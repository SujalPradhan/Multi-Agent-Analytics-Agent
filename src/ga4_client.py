"""
GA4 Data API Client

Wrapper for Google Analytics 4 Data API with:
- Service account authentication from credentials.json
- Dynamic propertyId support (required, no fallback)
- RunReport execution with retry logic
- Response parsing to structured dict
"""

import logging
import time
from typing import List, Dict, Any, Optional
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    Dimension,
    Metric,
    DateRange,
    RunReportResponse,
    FilterExpression,
    FilterExpressionList,
    Filter,
    OrderBy,
)
from google.oauth2.service_account import Credentials
from google.api_core.exceptions import GoogleAPIError, ResourceExhausted

logger = logging.getLogger(__name__)


class GA4ClientError(Exception):
    """Base exception for GA4 client errors"""
    pass


class GA4AuthenticationError(GA4ClientError):
    """Authentication failed with credentials"""
    pass


class GA4PropertyError(GA4ClientError):
    """Invalid or missing property ID"""
    pass


class GA4APIError(GA4ClientError):
    """GA4 API call failed"""
    pass


class GA4Client:
    """
    Google Analytics 4 Data API client.
    
    Handles authentication, report execution, and response parsing.
    Includes retry logic for transient errors and rate limits.
    """
    
    # GA4 Data API scopes
    SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']
    
    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1  # seconds
    
    # Timeout configuration (PRD requirement: 30 seconds)
    REQUEST_TIMEOUT = 30  # seconds
    
    def __init__(self, credentials_path: str):
        """
        Initialize GA4 client with service account credentials.
        
        Args:
            credentials_path: Path to credentials.json file
            
        Raises:
            GA4AuthenticationError: If credentials are invalid
        """
        self.credentials_path = credentials_path
        self.client: Optional[BetaAnalyticsDataClient] = None
        self._connect()
    
    def _connect(self):
        """Establish connection to GA4 Data API with timeout configuration"""
        try:
            from google.api_core import client_options
            
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES
            )
            
            # Configure client with timeout (PRD requirement: 30 seconds)
            self.client = BetaAnalyticsDataClient(
                credentials=credentials,
            )
            logger.info("Connected to GA4 Data API (timeout: %ds)", self.REQUEST_TIMEOUT)
        except FileNotFoundError:
            raise GA4AuthenticationError(
                f"Credentials file not found: {self.credentials_path}"
            )
        except Exception as e:
            raise GA4AuthenticationError(
                f"Failed to authenticate with GA4: {str(e)}"
            )
    
    def validate_property_id(self, property_id: Optional[str]) -> str:
        """
        Validate and format property ID.
        
        Args:
            property_id: GA4 property ID (numeric string)
            
        Returns:
            Formatted property ID with 'properties/' prefix
            
        Raises:
            GA4PropertyError: If property ID is missing or invalid
        """
        if not property_id:
            raise GA4PropertyError(
                "GA4 Property ID is required. Please provide 'propertyId' in your request "
                "(e.g., '123456789'). You can find this in Google Analytics under "
                "Admin > Property Settings."
            )
        
        # Remove any existing prefix
        clean_id = property_id.replace('properties/', '').strip()
        
        # Validate format (should be numeric)
        if not clean_id.isdigit():
            raise GA4PropertyError(
                f"Invalid Property ID format: '{property_id}'. "
                "Property ID should be a numeric value (e.g., '123456789')."
            )
        
        return f"properties/{clean_id}"
    
    def run_report(
        self,
        property_id: str,
        metrics: List[str],
        dimensions: Optional[List[str]] = None,
        start_date: str = "7daysAgo",
        end_date: str = "today",
        limit: int = 10000,
        dimension_filter: Optional[Dict[str, Any]] = None,
        metric_filter: Optional[Dict[str, Any]] = None,
        order_bys: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Execute a GA4 RunReport request.
        
        Args:
            property_id: GA4 property ID
            metrics: List of metric names (e.g., ['users', 'sessions'])
            dimensions: Optional list of dimension names (e.g., ['pagePath'])
            start_date: Start date in GA4 format (e.g., '7daysAgo', '2024-01-01')
            end_date: End date in GA4 format (e.g., 'today', '2024-01-31')
            limit: Maximum rows to return (default 10000)
            dimension_filter: Optional dimension filter config
                Example: {"field": "pagePath", "match_type": "contains", "value": "/pricing"}
                         {"and": [{"field": "pagePath", ...}, {"field": "country", ...}]}
            metric_filter: Optional metric filter config  
                Example: {"field": "sessions", "operation": "greater_than", "value": 100}
            order_bys: Optional list of ordering configs
                Example: [{"field": "sessions", "desc": True}]
                         [{"dimension": "date", "desc": False}]
            
        Returns:
            Dict with structure:
            {
                "rows": [{"dimension1": value, "metric1": value, ...}, ...],
                "row_count": int,
                "metadata": {
                    "property_id": str,
                    "metrics": List[str],
                    "dimensions": List[str],
                    "date_range": {"start": str, "end": str},
                    "filters": {...},
                    "order_by": [...]
                }
            }
            
        Raises:
            GA4PropertyError: Invalid property ID
            GA4APIError: API call failed after retries
        """
        # Validate and format property ID
        formatted_property = self.validate_property_id(property_id)
        
        # Build request
        request = RunReportRequest(
            property=formatted_property,
            metrics=[Metric(name=m) for m in metrics],
            dimensions=[Dimension(name=d) for d in (dimensions or [])],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            limit=limit
        )
        
        # Add dimension filter if provided
        if dimension_filter:
            request.dimension_filter = self._build_filter_expression(dimension_filter, is_dimension=True)
        
        # Add metric filter if provided
        if metric_filter:
            request.metric_filter = self._build_filter_expression(metric_filter, is_dimension=False)
        
        # Add ordering if provided
        if order_bys:
            request.order_bys = self._build_order_bys(order_bys)
        
        # Execute with retry
        response = self._execute_with_retry(request)
        
        # Parse response
        return self._parse_response(
            response=response,
            property_id=property_id,
            metrics=metrics,
            dimensions=dimensions or [],
            start_date=start_date,
            end_date=end_date,
            dimension_filter=dimension_filter,
            metric_filter=metric_filter,
            order_bys=order_bys
        )
    
    def _execute_with_retry(self, request: RunReportRequest) -> RunReportResponse:
        """
        Execute request with retry logic for transient errors.
        
        Silently retries up to 3 times on rate limits and transient errors.
        
        Args:
            request: GA4 RunReportRequest
            
        Returns:
            GA4 RunReportResponse
            
        Raises:
            GA4APIError: If all retries exhausted
        """
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.run_report(
                    request,
                    timeout=self.REQUEST_TIMEOUT
                )
                return response
                
            except ResourceExhausted as e:
                # Rate limit - retry silently
                last_error = e
                wait_time = self.BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"GA4 rate limit hit, retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                time.sleep(wait_time)
                
            except GoogleAPIError as e:
                # Check if transient error
                if self._is_transient_error(e):
                    last_error = e
                    wait_time = self.BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"GA4 transient error, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    time.sleep(wait_time)
                else:
                    # Non-transient error, fail immediately
                    raise GA4APIError(f"GA4 API error: {str(e)}")
                    
            except Exception as e:
                raise GA4APIError(f"Unexpected error calling GA4 API: {str(e)}")
        
        # All retries exhausted
        raise GA4APIError(
            "GA4 API temporarily unavailable after multiple retries. "
            "Please try again in a moment."
        )
    
    def _is_transient_error(self, error: GoogleAPIError) -> bool:
        """Check if error is transient and worth retrying"""
        transient_codes = [500, 502, 503, 504]  # Server errors
        if hasattr(error, 'code') and error.code in transient_codes:
            return True
        # Check error message for common transient patterns
        error_str = str(error).lower()
        transient_patterns = ['timeout', 'unavailable', 'internal', 'connection']
        return any(pattern in error_str for pattern in transient_patterns)
    
    def _parse_response(
        self,
        response: RunReportResponse,
        property_id: str,
        metrics: List[str],
        dimensions: List[str],
        start_date: str,
        end_date: str,
        dimension_filter: Optional[Dict[str, Any]] = None,
        metric_filter: Optional[Dict[str, Any]] = None,
        order_bys: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Parse GA4 response into structured dict.
        
        Args:
            response: GA4 RunReportResponse
            property_id: Original property ID
            metrics: Requested metrics
            dimensions: Requested dimensions
            start_date: Start date used
            end_date: End date used
            dimension_filter: Applied dimension filter
            metric_filter: Applied metric filter
            order_bys: Applied ordering
            
        Returns:
            Structured dict with rows and metadata
        """
        rows = []
        
        # Get header names from response
        dimension_headers = [h.name for h in response.dimension_headers]
        metric_headers = [h.name for h in response.metric_headers]
        
        for row in response.rows:
            row_dict = {}
            
            # Add dimension values
            for i, dim_value in enumerate(row.dimension_values):
                if i < len(dimension_headers):
                    row_dict[dimension_headers[i]] = dim_value.value
            
            # Add metric values (convert to appropriate type)
            for i, metric_value in enumerate(row.metric_values):
                if i < len(metric_headers):
                    row_dict[metric_headers[i]] = self._parse_metric_value(
                        metric_value.value,
                        metric_headers[i]
                    )
            
            rows.append(row_dict)
        
        return {
            "rows": rows,
            "row_count": len(rows),
            "metadata": {
                "property_id": property_id,
                "metrics": metrics,
                "dimensions": dimensions,
                "date_range": {
                    "start": start_date,
                    "end": end_date
                },
                "filters": {
                    "dimension_filter": dimension_filter,
                    "metric_filter": metric_filter
                } if dimension_filter or metric_filter else None,
                "order_by": order_bys
            }
        }
    
    def _parse_metric_value(self, value: str, metric_name: str) -> Any:
        """
        Parse metric value to appropriate Python type.
        
        Args:
            value: String value from GA4
            metric_name: Name of the metric
            
        Returns:
            int, float, or original string
        """
        try:
            # Check if it's a percentage/rate metric
            rate_metrics = [
                'bounceRate', 'engagementRate', 'conversionRate',
                'crashFreeUsersRate', 'userEngagementDuration'
            ]
            
            if metric_name in rate_metrics or '.' in value:
                return round(float(value), 4)
            else:
                return int(float(value))
        except (ValueError, TypeError):
            return value
    
    def _build_filter_expression(
        self,
        filter_config: Dict[str, Any],
        is_dimension: bool = True
    ) -> FilterExpression:
        """
        Build a GA4 FilterExpression from config dict.
        
        Args:
            filter_config: Filter configuration dict
                Simple: {"field": "pagePath", "match_type": "contains", "value": "/pricing"}
                AND: {"and": [filter1, filter2, ...]}
                OR: {"or": [filter1, filter2, ...]}
                NOT: {"not": filter}
            is_dimension: True for dimension filters, False for metric filters
            
        Returns:
            GA4 FilterExpression
        """
        # Handle compound filters (AND, OR, NOT)
        if "and" in filter_config:
            return FilterExpression(
                and_group=FilterExpressionList(
                    expressions=[
                        self._build_filter_expression(f, is_dimension)
                        for f in filter_config["and"]
                    ]
                )
            )
        
        if "or" in filter_config:
            return FilterExpression(
                or_group=FilterExpressionList(
                    expressions=[
                        self._build_filter_expression(f, is_dimension)
                        for f in filter_config["or"]
                    ]
                )
            )
        
        if "not" in filter_config:
            return FilterExpression(
                not_expression=self._build_filter_expression(
                    filter_config["not"], is_dimension
                )
            )
        
        # Handle simple filter
        field_name = filter_config.get("field")
        value = filter_config.get("value")
        
        if is_dimension:
            # Dimension filter (string matching)
            match_type = filter_config.get("match_type", "exact").upper()
            
            # Map match types to GA4 enum values
            match_type_map = {
                "EXACT": Filter.StringFilter.MatchType.EXACT,
                "BEGINS_WITH": Filter.StringFilter.MatchType.BEGINS_WITH,
                "ENDS_WITH": Filter.StringFilter.MatchType.ENDS_WITH,
                "CONTAINS": Filter.StringFilter.MatchType.CONTAINS,
                "FULL_REGEXP": Filter.StringFilter.MatchType.FULL_REGEXP,
                "PARTIAL_REGEXP": Filter.StringFilter.MatchType.PARTIAL_REGEXP,
            }
            
            ga4_match_type = match_type_map.get(
                match_type, 
                Filter.StringFilter.MatchType.EXACT
            )
            
            case_sensitive = filter_config.get("case_sensitive", False)
            
            return FilterExpression(
                filter=Filter(
                    field_name=field_name,
                    string_filter=Filter.StringFilter(
                        match_type=ga4_match_type,
                        value=str(value),
                        case_sensitive=case_sensitive
                    )
                )
            )
        else:
            # Metric filter (numeric comparison)
            operation = filter_config.get("operation", "equal").upper()
            
            # Map operations to GA4 enum values
            operation_map = {
                "EQUAL": Filter.NumericFilter.Operation.EQUAL,
                "LESS_THAN": Filter.NumericFilter.Operation.LESS_THAN,
                "LESS_THAN_OR_EQUAL": Filter.NumericFilter.Operation.LESS_THAN_OR_EQUAL,
                "GREATER_THAN": Filter.NumericFilter.Operation.GREATER_THAN,
                "GREATER_THAN_OR_EQUAL": Filter.NumericFilter.Operation.GREATER_THAN_OR_EQUAL,
            }
            
            ga4_operation = operation_map.get(
                operation,
                Filter.NumericFilter.Operation.EQUAL
            )
            
            # Determine if value is int or double
            if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
                numeric_value = Filter.NumericFilter.NumericValue(int64_value=int(value))
            else:
                numeric_value = Filter.NumericFilter.NumericValue(double_value=float(value))
            
            return FilterExpression(
                filter=Filter(
                    field_name=field_name,
                    numeric_filter=Filter.NumericFilter(
                        operation=ga4_operation,
                        value=numeric_value
                    )
                )
            )
    
    def _build_order_bys(
        self,
        order_configs: List[Dict[str, Any]]
    ) -> List[OrderBy]:
        """
        Build GA4 OrderBy list from config.
        
        Args:
            order_configs: List of ordering configs
                Example: [{"field": "sessions", "desc": True}]
                         [{"dimension": "date", "desc": False}]
                         [{"metric": "users", "desc": True}]
                         
        Returns:
            List of GA4 OrderBy objects
        """
        order_bys = []
        
        for config in order_configs:
            desc = config.get("desc", True)  # Default to descending
            
            # Determine if metric or dimension ordering
            if "metric" in config or "field" in config:
                # Metric ordering (most common)
                field = config.get("metric") or config.get("field")
                order_bys.append(
                    OrderBy(
                        metric=OrderBy.MetricOrderBy(metric_name=field),
                        desc=desc
                    )
                )
            elif "dimension" in config:
                # Dimension ordering
                field = config.get("dimension")
                order_type = config.get("order_type", "ALPHANUMERIC").upper()
                
                order_type_map = {
                    "ALPHANUMERIC": OrderBy.DimensionOrderBy.OrderType.ALPHANUMERIC,
                    "CASE_INSENSITIVE_ALPHANUMERIC": OrderBy.DimensionOrderBy.OrderType.CASE_INSENSITIVE_ALPHANUMERIC,
                    "NUMERIC": OrderBy.DimensionOrderBy.OrderType.NUMERIC,
                }
                
                ga4_order_type = order_type_map.get(
                    order_type,
                    OrderBy.DimensionOrderBy.OrderType.ALPHANUMERIC
                )
                
                order_bys.append(
                    OrderBy(
                        dimension=OrderBy.DimensionOrderBy(
                            dimension_name=field,
                            order_type=ga4_order_type
                        ),
                        desc=desc
                    )
                )
        
        return order_bys

    def test_connection(self, property_id: str) -> bool:
        """
        Test connection to a GA4 property.
        
        Args:
            property_id: GA4 property ID to test
            
        Returns:
            True if connection successful
            
        Raises:
            GA4PropertyError: If property ID invalid
            GA4APIError: If connection failed
        """
        try:
            # Run minimal report to test access
            self.run_report(
                property_id=property_id,
                metrics=['sessions'],
                start_date='yesterday',
                end_date='yesterday',
                limit=1
            )
            logger.info(f"Successfully connected to GA4 property: {property_id}")
            return True
        except GA4PropertyError:
            raise
        except Exception as e:
            raise GA4APIError(
                f"Failed to connect to GA4 property {property_id}: {str(e)}"
            )
