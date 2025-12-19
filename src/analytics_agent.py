"""
Analytics Agent

GA4 query processing agent with 4-stage pipeline:
1. Query Parser - LLM extracts metrics, dimensions, dates, json_flag
2. Validator - Check against allowlist, suggest alternatives on error
3. GA4 Executor - Execute report via ga4_client
4. Response Synthesizer - Format output (NL/JSON/Hybrid)

Features:
- Core metrics by default, extended metrics auto-enabled by context
- 7-day date range fallback
- Explicit errors with closest-match suggestions
- Transparent acknowledgment for extended metrics
"""

import logging
import difflib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from ga4_client import GA4Client, GA4ClientError, GA4PropertyError, GA4APIError
from llm_client import LLMClient, LLMPromptBuilder
from response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class AnalyticsAgentError(Exception):
    """Base exception for Analytics Agent errors"""
    pass


class ValidationError(AnalyticsAgentError):
    """Invalid metric or dimension"""
    pass


class AnalyticsAgent:
    """
    GA4 Analytics Agent for natural language query processing.
    
    Processes queries through 4-stage pipeline:
    Query → Parse → Validate → Execute → Synthesize → Response
    """
    
    # ===== METRIC/DIMENSION ALLOWLISTS =====
    
    # Core metrics (always available)
    CORE_METRICS = {
        'activeUsers': 'Users who had an engaged session',
        'newUsers': 'Number of first-time users',
        'sessions': 'Total number of sessions',
        'screenPageViews': 'Total page/screen views',
        'bounceRate': 'Percentage of single-page sessions',
        'averageSessionDuration': 'Average session length in seconds',
        'sessionsPerUser': 'Average sessions per user',
        'engagedSessions': 'Sessions with engagement',
        'engagementRate': 'Percentage of engaged sessions',
    }
    
    # Extended metrics (auto-enabled by context)
    EXTENDED_METRICS = {
        'eventCount': 'Total number of events',
        'conversions': 'Total conversions',
        'totalRevenue': 'Total revenue from purchases',
        'ecommercePurchases': 'Number of purchases',
        'transactions': 'Total transactions',
        'itemRevenue': 'Revenue from items',
        'addToCarts': 'Add to cart events',
        'checkouts': 'Checkout events',
        'itemsViewed': 'Items viewed',
        'itemsPurchased': 'Items purchased',
    }
    
    # Keywords that trigger extended metrics
    EXTENDED_TRIGGERS = [
        'revenue', 'sales', 'transactions', 'purchase', 'ecommerce',
        'e-commerce', 'conversions', 'convert', 'events', 'event count',
        'cart', 'checkout', 'order', 'buy', 'bought', 'sold', 'money',
        'income', 'earnings', 'item'
    ]
    
    # Core dimensions (always available)
    CORE_DIMENSIONS = {
        'pagePath': 'Page URL path',
        'pageTitle': 'Page title',
        'deviceCategory': 'Device type (desktop/mobile/tablet)',
        'country': 'User country',
        'city': 'User city',
        'date': 'Date (YYYYMMDD format)',
        'sessionSource': 'Traffic source',
        'sessionMedium': 'Traffic medium',
        'sessionCampaignName': 'Campaign name',
        'browser': 'Browser name',
        'operatingSystem': 'Operating system',
        'language': 'User language',
        'landingPage': 'First page in session',
    }
    
    # Extended dimensions (auto-enabled by context)
    EXTENDED_DIMENSIONS = {
        'eventName': 'Event name',
        'transactionId': 'Transaction ID',
        'itemName': 'Product/item name',
        'itemCategory': 'Product category',
        'itemBrand': 'Product brand',
    }
    
    # Date range patterns
    DATE_PATTERNS = {
        'today': ('today', 'today'),
        'yesterday': ('yesterday', 'yesterday'),
        'last 7 days': ('7daysAgo', 'today'),
        'past week': ('7daysAgo', 'today'),
        'this week': ('7daysAgo', 'today'),
        'last 14 days': ('14daysAgo', 'today'),
        'last 30 days': ('30daysAgo', 'today'),
        'past month': ('30daysAgo', 'today'),
        'this month': ('startOfMonth', 'today'),
        'last 90 days': ('90daysAgo', 'today'),
        'last quarter': ('90daysAgo', 'today'),
    }
    
    DEFAULT_DATE_RANGE = ('7daysAgo', 'today')
    
    def __init__(
        self,
        llm_client: LLMClient,
        credentials_path: str,
        default_property_id: Optional[str] = None
    ):
        """
        Initialize Analytics Agent.
        
        Args:
            llm_client: LLM client for query parsing and synthesis
            credentials_path: Path to Google credentials.json
            default_property_id: Optional default GA4 property ID
        """
        self.llm_client = llm_client
        self.ga4_client = GA4Client(credentials_path)
        self.default_property_id = default_property_id
        self.response_formatter = ResponseFormatter()
        
        # Track if extended metrics were auto-enabled
        self._extended_enabled = False
        self._extended_reason = ""
    
    async def process(
        self,
        query: str,
        property_id: Optional[str] = None,
        json_requested: bool = False
    ) -> Dict[str, Any]:
        """
        Process a natural language analytics query.
        
        Args:
            query: Natural language query
            property_id: GA4 property ID (uses default if not provided)
            json_requested: Whether user explicitly requested JSON format
            
        Returns:
            Dict with answer, data, and agent_used
        """
        try:
            # Reset extended metrics tracking
            self._extended_enabled = False
            self._extended_reason = ""
            
            # Resolve property ID
            resolved_property_id = property_id or self.default_property_id
            if not resolved_property_id:
                raise GA4PropertyError(
                    "GA4 Property ID is required. Please provide 'propertyId' in your request "
                    "(e.g., '123456789'). You can find this in Google Analytics under "
                    "Admin > Property Settings."
                )
            
            # Stage 1: Parse query
            parsed = await self._parse_query(query)
            logger.info(f"Parsed query: {parsed}")
            
            # Stage 2: Resolve metric tier and validate
            metrics, dimensions = await self._resolve_and_validate(
                query=query,
                parsed_metrics=parsed.get('metrics', []),
                parsed_dimensions=parsed.get('dimensions', [])
            )
            
            # Stage 3: Execute GA4 report
            data = self.ga4_client.run_report(
                property_id=resolved_property_id,
                metrics=metrics,
                dimensions=dimensions,
                start_date=parsed.get('start_date', self.DEFAULT_DATE_RANGE[0]),
                end_date=parsed.get('end_date', self.DEFAULT_DATE_RANGE[1]),
                limit=parsed.get('limit', 100)
            )
            
            # Stage 4: Synthesize response
            return await self._synthesize_response(
                query=query,
                data=data,
                json_requested=json_requested,
                parsed=parsed
            )
            
        except GA4PropertyError as e:
            return {
                "answer": str(e),
                "data": None,
                "agent_used": "analytics"
            }
        except ValidationError as e:
            return {
                "answer": str(e),
                "data": None,
                "agent_used": "analytics"
            }
        except GA4APIError as e:
            return {
                "answer": f"Error querying Google Analytics: {str(e)}",
                "data": None,
                "agent_used": "analytics"
            }
        except Exception as e:
            logger.error(f"Analytics agent error: {e}", exc_info=True)
            return {
                "answer": f"An error occurred processing your analytics query: {str(e)}",
                "data": None,
                "agent_used": "analytics"
            }
    
    # ===== STAGE 1: QUERY PARSER =====
    
    async def _parse_query(self, query: str) -> Dict[str, Any]:
        """
        Parse natural language query using LLM.
        
        Extracts:
        - metrics: List of GA4 metric names
        - dimensions: List of GA4 dimension names
        - start_date: Start date in GA4 format
        - end_date: End date in GA4 format
        - limit: Number of results to return
        """
        # Build available fields list for LLM context
        all_metrics = {**self.CORE_METRICS, **self.EXTENDED_METRICS}
        all_dimensions = {**self.CORE_DIMENSIONS, **self.EXTENDED_DIMENSIONS}
        
        system_prompt = f"""You are a GA4 query parser. Extract analytics parameters from natural language queries.

Available METRICS (use exact names):
{self._format_fields_for_prompt(all_metrics)}

Available DIMENSIONS (use exact names):
{self._format_fields_for_prompt(all_dimensions)}

DATE FORMATS:
- Relative: "today", "yesterday", "7daysAgo", "30daysAgo", "90daysAgo"
- Special: "startOfMonth", "endOfMonth"
- Absolute: "YYYY-MM-DD"

RULES:
1. Extract only explicitly mentioned or clearly implied metrics/dimensions
2. Default to "users" if no metric is clear
3. Default date range is last 7 days (7daysAgo to today)
4. For "top N" queries, set limit to N (default 10)
5. Use exact field names from the lists above

Return JSON only with this structure:
{{
    "metrics": ["metric1", "metric2"],
    "dimensions": ["dimension1"],
    "start_date": "7daysAgo",
    "end_date": "today",
    "limit": 10,
    "reasoning": "Brief explanation of extraction"
}}"""

        messages = [
            LLMPromptBuilder.build_system_message(system_prompt),
            LLMPromptBuilder.build_user_message(f"Parse this query: {query}")
        ]
        
        try:
            result = self.llm_client.chat(
                messages=messages,
                model='flash',
                temperature=0.1,
                json_mode=True
            )
            
            # Ensure required fields
            if not result.get('metrics'):
                result['metrics'] = ['users']
            if not result.get('start_date'):
                result['start_date'] = self.DEFAULT_DATE_RANGE[0]
            if not result.get('end_date'):
                result['end_date'] = self.DEFAULT_DATE_RANGE[1]
            if not result.get('limit'):
                result['limit'] = 10
                
            return result
            
        except Exception as e:
            logger.warning(f"LLM parsing failed, using defaults: {e}")
            return {
                'metrics': ['users'],
                'dimensions': [],
                'start_date': self.DEFAULT_DATE_RANGE[0],
                'end_date': self.DEFAULT_DATE_RANGE[1],
                'limit': 10
            }
    
    def _format_fields_for_prompt(self, fields: Dict[str, str]) -> str:
        """Format fields dict for LLM prompt"""
        return '\n'.join(f"- {name}: {desc}" for name, desc in fields.items())
    
    # ===== STAGE 2: VALIDATOR =====
    
    async def _resolve_and_validate(
        self,
        query: str,
        parsed_metrics: List[str],
        parsed_dimensions: List[str]
    ) -> Tuple[List[str], List[str]]:
        """
        Resolve metric tier and validate all fields.
        
        Auto-enables extended metrics if query context requires them.
        Validates all metrics/dimensions and suggests alternatives on error.
        """
        # Check if extended metrics should be enabled
        self._check_extended_triggers(query, parsed_metrics, parsed_dimensions)
        
        # Build current allowlist based on tier
        valid_metrics = set(self.CORE_METRICS.keys())
        valid_dimensions = set(self.CORE_DIMENSIONS.keys())
        
        if self._extended_enabled:
            valid_metrics.update(self.EXTENDED_METRICS.keys())
            valid_dimensions.update(self.EXTENDED_DIMENSIONS.keys())
        
        # Validate metrics
        validated_metrics = []
        for metric in parsed_metrics:
            validated = self._validate_field(
                field=metric,
                valid_fields=valid_metrics,
                field_type='Metric'
            )
            validated_metrics.append(validated)
        
        # Validate dimensions
        validated_dimensions = []
        for dimension in parsed_dimensions:
            validated = self._validate_field(
                field=dimension,
                valid_fields=valid_dimensions,
                field_type='Dimension'
            )
            validated_dimensions.append(validated)
        
        return validated_metrics, validated_dimensions
    
    def _check_extended_triggers(
        self,
        query: str,
        metrics: List[str],
        dimensions: List[str]
    ):
        """Check if query context requires extended metrics"""
        query_lower = query.lower()
        
        # Check query text for trigger keywords
        for trigger in self.EXTENDED_TRIGGERS:
            if trigger in query_lower:
                self._extended_enabled = True
                self._extended_reason = f"query mentions '{trigger}'"
                logger.info(f"Extended metrics enabled: {self._extended_reason}")
                return
        
        # Check if parsed fields require extended tier
        extended_metric_names = set(self.EXTENDED_METRICS.keys())
        extended_dimension_names = set(self.EXTENDED_DIMENSIONS.keys())
        
        for metric in metrics:
            if metric in extended_metric_names:
                self._extended_enabled = True
                self._extended_reason = f"metric '{metric}' requires extended tier"
                logger.info(f"Extended metrics enabled: {self._extended_reason}")
                return
        
        for dimension in dimensions:
            if dimension in extended_dimension_names:
                self._extended_enabled = True
                self._extended_reason = f"dimension '{dimension}' requires extended tier"
                logger.info(f"Extended metrics enabled: {self._extended_reason}")
                return
    
    def _validate_field(
        self,
        field: str,
        valid_fields: set,
        field_type: str
    ) -> str:
        """
        Validate a single field against allowlist.
        
        Args:
            field: Field name to validate
            valid_fields: Set of valid field names
            field_type: 'Metric' or 'Dimension' for error messages
            
        Returns:
            Validated field name
            
        Raises:
            ValidationError: If field is invalid with suggestion
        """
        if field in valid_fields:
            return field
        
        # Field not found - find closest match
        all_fields = list(valid_fields)
        close_matches = difflib.get_close_matches(
            field.lower(),
            [f.lower() for f in all_fields],
            n=3,
            cutoff=0.5
        )
        
        if close_matches:
            # Map back to original case
            suggestions = []
            for match in close_matches:
                for original in all_fields:
                    if original.lower() == match:
                        suggestions.append(original)
                        break
            
            suggestion_str = ', '.join(f"'{s}'" for s in suggestions)
            raise ValidationError(
                f"{field_type} '{field}' is not valid. "
                f"Did you mean: {suggestion_str}? "
                f"Please use exact GA4 field names."
            )
        else:
            # No close match - list some valid options
            sample_fields = list(valid_fields)[:5]
            sample_str = ', '.join(f"'{s}'" for s in sample_fields)
            raise ValidationError(
                f"{field_type} '{field}' is not recognized. "
                f"Valid {field_type.lower()}s include: {sample_str}, and more. "
                f"Please check GA4 documentation for exact field names."
            )
    
    # ===== STAGE 4: RESPONSE SYNTHESIZER =====
    
    async def _synthesize_response(
        self,
        query: str,
        data: Dict[str, Any],
        json_requested: bool,
        parsed: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synthesize final response in appropriate format.
        
        Format selection:
        - JSON requested: Strict JSON
        - >10 rows: Hybrid (NL + data)
        - Otherwise: Pure NL
        """
        row_count = data.get('row_count', 0)
        
        # Build acknowledgment prefix if extended metrics were used
        acknowledgment = ""
        if self._extended_enabled:
            acknowledgment = f"(Note: Including extended metrics to answer your {self._extended_reason}.) "
        
        if json_requested:
            # Strict JSON mode
            return {
                "answer": f"{acknowledgment}Results returned in JSON format.",
                "data": data,
                "agent_used": "analytics"
            }
        
        # Generate natural language explanation
        nl_response = await self._generate_nl_response(query, data, parsed)
        
        if row_count > 10:
            # Hybrid mode - NL + data
            return {
                "answer": f"{acknowledgment}{nl_response}",
                "data": data,
                "agent_used": "analytics"
            }
        else:
            # Pure NL mode
            return {
                "answer": f"{acknowledgment}{nl_response}",
                "data": None,
                "agent_used": "analytics"
            }
    
    async def _generate_nl_response(
        self,
        query: str,
        data: Dict[str, Any],
        parsed: Dict[str, Any]
    ) -> str:
        """Generate natural language explanation of data"""
        
        # Handle empty results
        if data.get('row_count', 0) == 0:
            return (
                f"No data found for the specified query. This could mean:\n"
                f"- No traffic during the date range ({parsed.get('start_date')} to {parsed.get('end_date')})\n"
                f"- The requested dimensions/metrics have no recorded values\n"
                f"- The property ID may not have the expected data"
            )
        
        # Build context for LLM
        system_prompt = """You are a data analyst explaining Google Analytics results clearly and concisely.

RULES:
1. Start with a direct answer to the user's question
2. Highlight key numbers and insights
3. Use percentages when comparing values
4. Keep response under 200 words
5. Be conversational but professional
6. If data has multiple rows, summarize patterns
7. Include the date range context"""

        # Limit data for prompt (first 20 rows)
        display_data = data.copy()
        if len(display_data.get('rows', [])) > 20:
            display_data['rows'] = display_data['rows'][:20]
            display_data['note'] = f"Showing first 20 of {data['row_count']} rows"
        
        user_prompt = f"""Original question: {query}

Date range: {parsed.get('start_date')} to {parsed.get('end_date')}
Metrics requested: {', '.join(parsed.get('metrics', []))}
Dimensions: {', '.join(parsed.get('dimensions', [])) or 'None (aggregate)'}

Data:
{display_data}

Provide a clear, natural language explanation of these results."""

        messages = [
            LLMPromptBuilder.build_system_message(system_prompt),
            LLMPromptBuilder.build_user_message(user_prompt)
        ]
        
        try:
            response = self.llm_client.chat(
                messages=messages,
                model='flash',
                temperature=0.3
            )
            return response
        except Exception as e:
            logger.warning(f"NL generation failed: {e}")
            # Fallback to basic response
            rows = data.get('rows', [])
            if rows:
                first_row = rows[0]
                metrics_str = ', '.join(f"{k}: {v}" for k, v in first_row.items())
                return f"Results for your query: {metrics_str} (and {len(rows)-1} more rows)"
            return "Query completed but could not generate explanation."
