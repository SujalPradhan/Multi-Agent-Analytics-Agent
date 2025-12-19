"""
SEO Agent - Screaming Frog Data Analysis

SEO DATA SOURCE GUARANTEE:
- Primary source: Google Sheets API (Screaming Frog export)
- Caching: In-memory only, session-scoped
- NO static CSVs or local files permitted
- Fetches fresh data every session start

4-Stage Pipeline:
1. Query Parser - LLM extracts filters, conditions, groupings from NL
2. Schema Resolver - Maps user terms to actual columns via alias map + fuzzy matching
3. Data Processor - Applies pandas operations on cached DataFrame
4. Response Synthesizer - Formats output (NL/JSON/Hybrid)

Features:
- Dynamic column detection from sheet headers
- Semantic alias map for user-friendly field names
- 80% similarity threshold for fuzzy matching (fails gracefully if unmet)
- Graceful degradation when SHEET_ID is not configured
"""

import logging
import difflib
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

from sheets_client import SheetsClient, SheetsClientError, SheetsNotFoundError, SheetsAPIError
from llm_client import LLMClient, LLMPromptBuilder
from response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class SEOAgentError(Exception):
    """Base exception for SEO Agent errors"""
    pass


class SchemaResolutionError(SEOAgentError):
    """Failed to resolve field name to column"""
    pass


class SEOAgent:
    """
    SEO Agent for Screaming Frog data analysis.
    
    Processes natural language queries about SEO data from Google Sheets.
    Uses 4-stage pipeline: Parse → Resolve → Process → Synthesize
    
    SEO DATA SOURCE GUARANTEE:
    - Primary source: Google Sheets API (Screaming Frog export)
    - Caching: In-memory only, session-scoped
    - NO static CSVs or local files permitted
    """
    
    # ===== SEMANTIC ALIAS MAP =====
    # Maps user-friendly terms to actual Screaming Frog column names
    # This provides robustness to schema variations
    
    COLUMN_ALIASES = {
        # URL/Address
        "url": "Address",
        "urls": "Address",
        "address": "Address",
        "page": "Address",
        "pages": "Address",
        "link": "Address",
        "links": "Address",
        
        # Title
        "title": "Title 1",
        "page title": "Title 1",
        "titles": "Title 1",
        "title tag": "Title 1",
        "title tags": "Title 1",
        "title 1": "Title 1",
        "title length": "Title 1 Length",
        "title len": "Title 1 Length",
        
        # Meta Description
        "meta description": "Meta Description 1",
        "meta descriptions": "Meta Description 1",
        "description": "Meta Description 1",
        "descriptions": "Meta Description 1",
        "meta desc": "Meta Description 1",
        "meta description 1": "Meta Description 1",
        "meta description length": "Meta Description 1 Length",
        "description length": "Meta Description 1 Length",
        
        # H1
        "h1": "H1-1",
        "h1s": "H1-1",
        "h1 tag": "H1-1",
        "h1 tags": "H1-1",
        "heading": "H1-1",
        "headings": "H1-1",
        "h1-1": "H1-1",
        "h1 length": "H1-1 Length",
        
        # H2
        "h2": "H2-1",
        "h2s": "H2-1",
        "h2-1": "H2-1",
        
        # Status Code
        "status": "Status Code",
        "status code": "Status Code",
        "http status": "Status Code",
        "response code": "Status Code",
        "status codes": "Status Code",
        
        # Indexability
        "indexable": "Indexability",
        "indexability": "Indexability",
        "index status": "Indexability",
        "indexed": "Indexability",
        "indexability status": "Indexability Status",
        
        # Word Count
        "word count": "Word Count",
        "words": "Word Count",
        "content length": "Word Count",
        
        # Canonical
        "canonical": "Canonical Link Element 1",
        "canonical url": "Canonical Link Element 1",
        "canonical link": "Canonical Link Element 1",
        
        # Redirects
        "redirect": "Redirect URL",
        "redirect url": "Redirect URL",
        "redirects": "Redirect URL",
        "redirect to": "Redirect URL",
        
        # Content Type
        "content type": "Content Type",
        "content": "Content Type",
        "type": "Content Type",
        
        # Links
        "inlinks": "Inlinks",
        "internal links": "Inlinks",
        "outlinks": "Outlinks",
        "external links": "Outlinks",
        "unique inlinks": "Unique Inlinks",
        "unique outlinks": "Unique Outlinks",
        
        # Size/Performance
        "size": "Size (Bytes)",
        "page size": "Size (Bytes)",
        "response time": "Response Time",
        "load time": "Response Time",
        
        # Crawl
        "crawl depth": "Crawl Depth",
        "depth": "Crawl Depth",
        "level": "Crawl Depth",
    }
    
    # Fuzzy matching threshold (80%)
    FUZZY_THRESHOLD = 0.8
    
    def __init__(
        self,
        llm_client: LLMClient,
        sheets_client: SheetsClient,
        default_sheet_id: Optional[str] = None
    ):
        """
        Initialize SEO Agent.
        
        Args:
            llm_client: LLM client for query parsing and synthesis
            sheets_client: Google Sheets client for data access
            default_sheet_id: Default Sheet ID for SEO data (optional)
        """
        self.llm_client = llm_client
        self.sheets_client = sheets_client
        self.default_sheet_id = default_sheet_id
        self.response_formatter = ResponseFormatter()
        
        # Track resolved columns for debugging
        self._resolved_columns: Dict[str, str] = {}
        self._available_columns: List[str] = []
        
        logger.info("SEO Agent initialized")
        logger.info(f"Default Sheet ID: {default_sheet_id or 'Not set'}")
    
    async def process(
        self,
        query: str,
        sheet_id: Optional[str] = None,
        json_requested: bool = False
    ) -> Dict[str, Any]:
        """
        Process a natural language SEO query.
        
        Args:
            query: Natural language query
            sheet_id: Google Sheets ID (uses default if not provided)
            json_requested: Whether user explicitly requested JSON format
            
        Returns:
            Dict with answer, data, and agent_used
        """
        try:
            # Resolve sheet ID
            resolved_sheet_id = sheet_id or self.default_sheet_id
            
            # Graceful handling if SHEET_ID is not configured
            if not resolved_sheet_id:
                return {
                    "answer": (
                        "SEO analysis requires a Google Sheet ID. "
                        "Please configure SHEET_ID in your environment variables. "
                        "The Sheet should contain Screaming Frog export data."
                    ),
                    "data": None,
                    "agent_used": "seo"
                }
            
            # Stage 1: Fetch data and detect schema
            df = self.sheets_client.fetch_sheet(resolved_sheet_id)
            self._available_columns = list(df.columns)
            
            if df.empty:
                return {
                    "answer": "The SEO data sheet is empty. Please ensure the Google Sheet contains Screaming Frog export data.",
                    "data": None,
                    "agent_used": "seo"
                }
            
            # Stage 2: Parse query
            parsed = await self._parse_query(query, self._available_columns)
            logger.info(f"Parsed query: {parsed}")
            
            # Stage 3: Resolve columns and validate
            resolution_result = self._resolve_columns(parsed)
            
            if resolution_result.get('errors'):
                # Fail entirely if required fields couldn't be resolved
                return {
                    "answer": self._format_resolution_errors(resolution_result['errors']),
                    "data": None,
                    "agent_used": "seo"
                }
            
            # Stage 4: Process data
            result_df, processing_info = self._process_data(
                df=df,
                parsed=parsed,
                resolved_columns=resolution_result['resolved']
            )
            
            # Stage 5: Synthesize response
            return await self._synthesize_response(
                query=query,
                result_df=result_df,
                processing_info=processing_info,
                json_requested=json_requested,
                parsed=parsed
            )
            
        except SheetsNotFoundError as e:
            return {
                "answer": str(e),
                "data": None,
                "agent_used": "seo"
            }
        except SheetsAPIError as e:
            return {
                "answer": f"Error accessing SEO data: {str(e)}",
                "data": None,
                "agent_used": "seo"
            }
        except SchemaResolutionError as e:
            return {
                "answer": str(e),
                "data": None,
                "agent_used": "seo"
            }
        except Exception as e:
            logger.error(f"SEO agent error: {e}", exc_info=True)
            return {
                "answer": f"An error occurred processing your SEO query: {str(e)}",
                "data": None,
                "agent_used": "seo"
            }
    
    # ===== STAGE 1: QUERY PARSER =====
    
    async def _parse_query(self, query: str, available_columns: List[str]) -> Dict[str, Any]:
        """
        Parse natural language query using LLM.
        
        Extracts:
        - filters: List of filter conditions
        - select_columns: Columns to include in output
        - group_by: Column to group by (if any)
        - aggregations: Aggregation operations
        - limit: Number of results
        - sort_by: Sort column and direction
        """
        system_prompt = f"""You are an SEO data query parser. Extract query parameters from natural language.

The data comes from a Screaming Frog SEO spider export with these columns:
{', '.join(available_columns[:30])}{'...' if len(available_columns) > 30 else ''}

Common field aliases you should recognize:
- "url", "page", "address" → Address column
- "title", "page title", "title tag" → Title 1 column
- "meta description", "description" → Meta Description 1 column
- "h1", "heading" → H1-1 column
- "status", "status code" → Status Code column
- "indexable", "indexability" → Indexability column

Extract the following from the query:

1. FILTERS: Conditions to filter rows. Each filter has:
   - field: The column name (use user's term, will be resolved later)
   - operator: "equals", "not_equals", "contains", "not_contains", "greater_than", "less_than", "is_empty", "is_not_empty"
   - value: The comparison value (if applicable)

2. SELECT_COLUMNS: Columns to include in output (use user terms)

3. GROUP_BY: Column to group results by (if aggregation needed)

4. AGGREGATIONS: Operations like "count", "sum", "average", "percentage"

5. LIMIT: Number of results (default 100)

6. SORT_BY: Column and direction ("asc" or "desc")

Return JSON only:
{{
    "filters": [
        {{"field": "status code", "operator": "equals", "value": "404"}}
    ],
    "select_columns": ["url", "title", "status code"],
    "group_by": null,
    "aggregation": null,
    "limit": 100,
    "sort_by": {{"field": null, "direction": "asc"}},
    "reasoning": "Brief explanation"
}}

Examples:
- "URLs with missing meta descriptions" → filter: meta description is_empty
- "Pages with 404 errors" → filter: status code equals 404
- "Title tags longer than 60 characters" → filter: title length greater_than 60
- "Group pages by indexability" → group_by: indexability, aggregation: count
- "Percentage of indexable pages" → aggregation: percentage, filter on indexability"""

        messages = [
            LLMPromptBuilder.build_system_message(system_prompt),
            LLMPromptBuilder.build_user_message(f"Parse this SEO query: {query}")
        ]
        
        try:
            result = self.llm_client.chat(
                messages=messages,
                model='flash',
                temperature=0.1,
                json_mode=True
            )
            
            # Ensure required fields with defaults
            if not isinstance(result, dict):
                result = {}
            
            result.setdefault('filters', [])
            result.setdefault('select_columns', ['Address'])
            result.setdefault('group_by', None)
            result.setdefault('aggregation', None)
            result.setdefault('limit', 100)
            result.setdefault('sort_by', {'field': None, 'direction': 'asc'})
            
            return result
            
        except Exception as e:
            logger.error(f"Query parsing error: {e}")
            # Return minimal defaults on parse failure
            return {
                'filters': [],
                'select_columns': ['Address'],
                'group_by': None,
                'aggregation': None,
                'limit': 100,
                'sort_by': {'field': None, 'direction': 'asc'}
            }
    
    # ===== STAGE 2: SCHEMA RESOLVER =====
    
    def _resolve_columns(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve user field names to actual column names.
        
        Uses:
        1. Exact match in COLUMN_ALIASES
        2. Fuzzy matching against actual columns (≥80% threshold)
        3. Fails gracefully if below threshold
        
        Args:
            parsed: Parsed query dict
            
        Returns:
            Dict with 'resolved' mappings and 'errors' list
        """
        resolved = {}
        errors = []
        warnings = []
        
        # Collect all field references from parsed query
        fields_to_resolve = set()
        
        # From filters (handle None)
        filters = parsed.get('filters') or []
        for f in filters:
            if isinstance(f, dict) and f.get('field'):
                fields_to_resolve.add(f['field'])
        
        # From select columns (handle None)
        select_columns = parsed.get('select_columns') or []
        for col in select_columns:
            if col:
                fields_to_resolve.add(col)
        
        # From group_by
        if parsed.get('group_by'):
            fields_to_resolve.add(parsed['group_by'])
        
        # From sort_by
        if parsed.get('sort_by', {}).get('field'):
            fields_to_resolve.add(parsed['sort_by']['field'])
        
        # Resolve each field
        for field in fields_to_resolve:
            result = self._resolve_single_column(field)
            
            if result['status'] == 'resolved':
                resolved[field] = result['column']
                if result.get('warning'):
                    warnings.append(result['warning'])
            elif result['status'] == 'error':
                errors.append(result['error'])
        
        return {
            'resolved': resolved,
            'errors': errors,
            'warnings': warnings
        }
    
    def _resolve_single_column(self, user_field: str) -> Dict[str, Any]:
        """
        Resolve a single user field to actual column name.
        
        Priority:
        1. Check COLUMN_ALIASES (exact match, case-insensitive)
        2. Check if user_field matches actual column directly
        3. Fuzzy match against actual columns (≥80% threshold)
        4. Fail with helpful error if no match
        
        Args:
            user_field: User-provided field name
            
        Returns:
            Dict with 'status', 'column', and optional 'error' or 'warning'
        """
        user_field_lower = user_field.lower().strip()
        
        # 1. Check alias map (case-insensitive)
        if user_field_lower in self.COLUMN_ALIASES:
            target_column = self.COLUMN_ALIASES[user_field_lower]
            
            # Verify target exists in actual columns
            if target_column in self._available_columns:
                return {'status': 'resolved', 'column': target_column}
            
            # Target doesn't exist, try fuzzy match on target
            fuzzy_result = self._fuzzy_match(target_column, self._available_columns)
            if fuzzy_result:
                return {
                    'status': 'resolved',
                    'column': fuzzy_result,
                    'warning': f"Mapped '{user_field}' to '{fuzzy_result}' (via alias)"
                }
        
        # 2. Check direct match against actual columns (case-insensitive)
        for col in self._available_columns:
            if col.lower() == user_field_lower:
                return {'status': 'resolved', 'column': col}
        
        # 3. Fuzzy match against actual columns
        fuzzy_result = self._fuzzy_match(user_field, self._available_columns)
        if fuzzy_result:
            return {
                'status': 'resolved',
                'column': fuzzy_result,
                'warning': f"Interpreted '{user_field}' as '{fuzzy_result}' (fuzzy match)"
            }
        
        # 4. Failed to resolve - provide helpful error
        suggestions = self._get_suggestions(user_field, self._available_columns, n=3)
        suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        
        return {
            'status': 'error',
            'error': f"Unknown field '{user_field}'.{suggestion_text} Available columns include: {', '.join(self._available_columns[:10])}{'...' if len(self._available_columns) > 10 else ''}"
        }
    
    def _fuzzy_match(self, term: str, candidates: List[str]) -> Optional[str]:
        """
        Find best fuzzy match above threshold.
        
        Args:
            term: Search term
            candidates: List of candidate strings
            
        Returns:
            Best match if above threshold, None otherwise
        """
        if not candidates:
            return None
        
        term_lower = term.lower()
        best_match = None
        best_ratio = 0.0
        
        for candidate in candidates:
            ratio = difflib.SequenceMatcher(
                None, 
                term_lower, 
                candidate.lower()
            ).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate
        
        # Only accept if above threshold
        if best_ratio >= self.FUZZY_THRESHOLD:
            logger.info(f"Fuzzy matched '{term}' to '{best_match}' ({best_ratio:.2%})")
            return best_match
        
        return None
    
    def _get_suggestions(self, term: str, candidates: List[str], n: int = 3) -> List[str]:
        """
        Get top N suggestions for a term (regardless of threshold).
        
        Args:
            term: Search term
            candidates: List of candidates
            n: Number of suggestions
            
        Returns:
            List of suggested matches
        """
        if not candidates:
            return []
        
        matches = difflib.get_close_matches(
            term.lower(),
            [c.lower() for c in candidates],
            n=n,
            cutoff=0.4  # Lower cutoff for suggestions
        )
        
        # Map back to original case
        result = []
        for match in matches:
            for candidate in candidates:
                if candidate.lower() == match and candidate not in result:
                    result.append(candidate)
                    break
        
        return result
    
    def _format_resolution_errors(self, errors: List[str]) -> str:
        """Format resolution errors into user-friendly message."""
        if len(errors) == 1:
            return errors[0]
        
        return "Could not resolve the following fields:\n" + "\n".join(f"• {e}" for e in errors)
    
    # ===== STAGE 3: DATA PROCESSOR =====
    
    def _process_data(
        self,
        df: pd.DataFrame,
        parsed: Dict[str, Any],
        resolved_columns: Dict[str, str]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Process data according to parsed query.
        
        Applies filters, grouping, aggregations, sorting, and limiting.
        
        Args:
            df: Source DataFrame
            parsed: Parsed query
            resolved_columns: User field → actual column mapping
            
        Returns:
            Tuple of (result DataFrame, processing info dict)
        """
        processing_info = {
            'original_rows': len(df),
            'filters_applied': [],
            'grouped_by': None,
            'aggregation': None
        }
        
        result_df = df.copy()
        
        # Apply filters (handle None)
        filters = parsed.get('filters') or []
        for filter_spec in filters:
            if not isinstance(filter_spec, dict):
                continue
            field = filter_spec.get('field')
            operator = filter_spec.get('operator', 'equals')
            value = filter_spec.get('value')
            
            if not field or field not in resolved_columns:
                continue
            
            actual_column = resolved_columns[field]
            
            if actual_column not in result_df.columns:
                continue
            
            before_count = len(result_df)
            result_df = self._apply_filter(result_df, actual_column, operator, value)
            after_count = len(result_df)
            
            processing_info['filters_applied'].append({
                'field': field,
                'column': actual_column,
                'operator': operator,
                'value': value,
                'rows_before': before_count,
                'rows_after': after_count
            })
        
        # Apply grouping and aggregation
        if parsed.get('group_by') and parsed['group_by'] in resolved_columns:
            group_column = resolved_columns[parsed['group_by']]
            aggregation = parsed.get('aggregation', 'count')
            
            if group_column in result_df.columns:
                result_df = self._apply_grouping(result_df, group_column, aggregation)
                processing_info['grouped_by'] = group_column
                processing_info['aggregation'] = aggregation
        
        # Apply sorting (handle None)
        sort_spec = parsed.get('sort_by') or {}
        if isinstance(sort_spec, dict) and sort_spec.get('field') and sort_spec['field'] in resolved_columns:
            sort_column = resolved_columns[sort_spec['field']]
            ascending = sort_spec.get('direction', 'asc') == 'asc'
            
            if sort_column in result_df.columns:
                result_df = result_df.sort_values(by=sort_column, ascending=ascending)
        
        # Apply limit
        limit = parsed.get('limit', 100)
        if limit and len(result_df) > limit:
            result_df = result_df.head(limit)
        
        # Select columns for output (handle None)
        select_columns = parsed.get('select_columns') or []
        if select_columns:
            actual_select = []
            for col in select_columns:
                if col and col in resolved_columns and resolved_columns[col] in result_df.columns:
                    actual_select.append(resolved_columns[col])
            
            if actual_select:
                # Keep any columns added by grouping
                for col in result_df.columns:
                    if col not in actual_select and col in ['count', 'sum', 'average', 'percentage']:
                        actual_select.append(col)
                result_df = result_df[actual_select]
        
        processing_info['final_rows'] = len(result_df)
        processing_info['final_columns'] = list(result_df.columns)
        
        return result_df, processing_info
    
    def _apply_filter(
        self,
        df: pd.DataFrame,
        column: str,
        operator: str,
        value: Any
    ) -> pd.DataFrame:
        """Apply a single filter to DataFrame."""
        try:
            if operator == 'equals':
                return df[df[column].astype(str).str.lower() == str(value).lower()]
            
            elif operator == 'not_equals':
                return df[df[column].astype(str).str.lower() != str(value).lower()]
            
            elif operator == 'contains':
                return df[df[column].astype(str).str.lower().str.contains(str(value).lower(), na=False)]
            
            elif operator == 'not_contains':
                return df[~df[column].astype(str).str.lower().str.contains(str(value).lower(), na=False)]
            
            elif operator == 'greater_than':
                # Try numeric comparison
                try:
                    return df[pd.to_numeric(df[column], errors='coerce') > float(value)]
                except:
                    return df[df[column].astype(str) > str(value)]
            
            elif operator == 'less_than':
                try:
                    return df[pd.to_numeric(df[column], errors='coerce') < float(value)]
                except:
                    return df[df[column].astype(str) < str(value)]
            
            elif operator == 'is_empty':
                return df[df[column].isna() | (df[column].astype(str).str.strip() == '')]
            
            elif operator == 'is_not_empty':
                return df[df[column].notna() & (df[column].astype(str).str.strip() != '')]
            
            else:
                logger.warning(f"Unknown operator: {operator}")
                return df
                
        except Exception as e:
            logger.error(f"Filter error on column '{column}': {e}")
            return df
    
    def _apply_grouping(
        self,
        df: pd.DataFrame,
        group_column: str,
        aggregation: str
    ) -> pd.DataFrame:
        """Apply grouping and aggregation."""
        try:
            if aggregation == 'count':
                result = df.groupby(group_column).size().reset_index(name='count')
                return result.sort_values('count', ascending=False)
            
            elif aggregation == 'percentage':
                counts = df.groupby(group_column).size()
                percentages = (counts / len(df) * 100).round(2)
                result = pd.DataFrame({
                    group_column: counts.index,
                    'count': counts.values,
                    'percentage': percentages.values
                })
                return result.sort_values('percentage', ascending=False)
            
            elif aggregation == 'sum':
                # Sum numeric columns
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    return df.groupby(group_column)[numeric_cols].sum().reset_index()
                return df.groupby(group_column).size().reset_index(name='count')
            
            elif aggregation == 'average':
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    return df.groupby(group_column)[numeric_cols].mean().reset_index()
                return df.groupby(group_column).size().reset_index(name='count')
            
            else:
                return df.groupby(group_column).size().reset_index(name='count')
                
        except Exception as e:
            logger.error(f"Grouping error: {e}")
            return df
    
    # ===== STAGE 4: RESPONSE SYNTHESIZER =====
    
    async def _synthesize_response(
        self,
        query: str,
        result_df: pd.DataFrame,
        processing_info: Dict[str, Any],
        json_requested: bool,
        parsed: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Synthesize final response from processed data.
        
        Handles NL, JSON, and Hybrid formats.
        """
        # Convert DataFrame to dict for response
        if result_df.empty:
            data_dict = {"rows": [], "columns": []}
        else:
            data_dict = {
                "rows": result_df.to_dict('records'),
                "columns": list(result_df.columns),
                "total_rows": len(result_df)
            }
        
        # JSON format requested
        if json_requested:
            return self.response_formatter.format_response(
                answer="Results returned in JSON format",
                data=data_dict,
                agent_used="seo",
                json_requested=True
            )
        
        # Generate natural language summary
        nl_answer = await self._generate_nl_summary(
            query=query,
            result_df=result_df,
            processing_info=processing_info,
            parsed=parsed
        )
        
        # Decide between NL and Hybrid
        if self._should_use_hybrid(result_df):
            return self.response_formatter.format_response(
                answer=nl_answer,
                data=data_dict,
                agent_used="seo",
                json_requested=False
            )
        
        return self.response_formatter.format_response(
            answer=nl_answer,
            data=None,
            agent_used="seo",
            json_requested=False
        )
    
    async def _generate_nl_summary(
        self,
        query: str,
        result_df: pd.DataFrame,
        processing_info: Dict[str, Any],
        parsed: Dict[str, Any]
    ) -> str:
        """Generate natural language summary of results."""
        
        if result_df.empty:
            return (
                f"No results found for your query. "
                f"Searched through {processing_info['original_rows']} rows "
                f"with {len(processing_info.get('filters_applied', []))} filter(s) applied."
            )
        
        # Build context for LLM
        sample_data = result_df.head(10).to_string(index=False)
        
        prompt = f"""Summarize these SEO analysis results in natural language.

Original Query: {query}

Processing Info:
- Original rows: {processing_info['original_rows']}
- Filters applied: {len(processing_info.get('filters_applied', []))}
- Final rows: {processing_info['final_rows']}
- Grouped by: {processing_info.get('grouped_by', 'None')}
- Aggregation: {processing_info.get('aggregation', 'None')}

Sample Results (first 10 rows):
{sample_data}

Provide a clear, helpful summary that:
1. Directly answers the user's question
2. Highlights key findings
3. Mentions important numbers/percentages
4. Provides actionable SEO insights if relevant

Keep the response concise but informative (2-4 sentences for simple queries, more for complex analysis)."""

        messages = [
            LLMPromptBuilder.build_system_message(
                "an SEO expert providing clear, actionable insights from Screaming Frog data"
            ),
            LLMPromptBuilder.build_user_message(prompt)
        ]
        
        try:
            response = self.llm_client.chat(
                messages=messages,
                model='flash',
                temperature=0.3
            )
            return response.strip()
        except Exception as e:
            logger.error(f"NL synthesis error: {e}")
            # Fallback to simple summary
            return (
                f"Found {len(result_df)} results matching your query "
                f"(filtered from {processing_info['original_rows']} total rows)."
            )
    
    def _should_use_hybrid(self, result_df: pd.DataFrame) -> bool:
        """Determine if hybrid response (NL + data) is appropriate."""
        # Use hybrid for medium-sized result sets
        if result_df.empty:
            return False
        
        row_count = len(result_df)
        return 10 <= row_count <= 100
