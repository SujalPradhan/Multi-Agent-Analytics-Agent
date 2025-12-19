"""
Response Formatter - Utility for formatting API responses

Handles the logic for determining and constructing appropriate
response formats (Natural Language, JSON, or Hybrid).
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """
    Utility class for formatting API responses.
    
    Determines appropriate format based on:
    - User's explicit request (JSON keyword)
    - Data payload size
    - Query complexity
    """
    
    # Thresholds for format decisions
    HYBRID_THRESHOLD_ROWS = 10
    HYBRID_THRESHOLD_COMPLEXITY = 5
    
    @staticmethod
    def format_response(
        answer: str,
        data: Optional[Dict[str, Any]] = None,
        agent_used: str = "unknown",
        json_requested: bool = False
    ) -> Dict[str, Any]:
        """
        Format response based on content and request type.
        
        Args:
            answer: Natural language answer or explanation
            data: Structured data (optional)
            agent_used: Which agent processed the query
            json_requested: Whether user explicitly requested JSON
        
        Returns:
            Formatted response dict
        """
        if json_requested:
            return ResponseFormatter._format_json(data, agent_used)
        
        if ResponseFormatter._should_use_hybrid(data):
            return ResponseFormatter._format_hybrid(answer, data, agent_used)
        
        return ResponseFormatter._format_natural_language(answer, agent_used)
    
    @staticmethod
    def _format_natural_language(
        answer: str,
        agent_used: str
    ) -> Dict[str, Any]:
        """
        Format as pure natural language response.
        
        Args:
            answer: Natural language explanation
            agent_used: Agent identifier
        
        Returns:
            Response dict with no data payload
        """
        return {
            "answer": answer,
            "data": None,
            "agent_used": agent_used
        }
    
    @staticmethod
    def _format_json(
        data: Optional[Dict[str, Any]],
        agent_used: str
    ) -> Dict[str, Any]:
        """
        Format as strict JSON response.
        
        Args:
            data: Structured data
            agent_used: Agent identifier
        
        Returns:
            Response dict with data payload and minimal explanation
        """
        return {
            "answer": "Results returned in JSON format",
            "data": data or {},
            "agent_used": agent_used
        }
    
    @staticmethod
    def _format_hybrid(
        answer: str,
        data: Dict[str, Any],
        agent_used: str
    ) -> Dict[str, Any]:
        """
        Format as hybrid response (NL + data).
        
        Args:
            answer: Natural language explanation
            data: Structured data
            agent_used: Agent identifier
        
        Returns:
            Response dict with both explanation and data
        """
        return {
            "answer": answer,
            "data": data,
            "agent_used": agent_used
        }
    
    @staticmethod
    def _should_use_hybrid(data: Optional[Dict[str, Any]]) -> bool:
        """
        Determine if response should be hybrid format.
        
        Use hybrid when:
        - Data payload is substantial (>10 rows)
        - Complex nested structure
        - Multiple data sources
        
        Args:
            data: Data dict to evaluate
        
        Returns:
            True if hybrid format appropriate
        """
        if not data:
            return False
        
        # Check for row count
        if 'rows' in data:
            row_count = len(data.get('rows', []))
            if row_count > ResponseFormatter.HYBRID_THRESHOLD_ROWS:
                logger.info(f"Using hybrid format: {row_count} rows")
                return True
        
        # Check for multiple data sources
        if isinstance(data, dict):
            source_keys = [k for k in data.keys() if k.startswith('source_')]
            if len(source_keys) >= 2:
                logger.info(f"Using hybrid format: {len(source_keys)} sources")
                return True
        
        # Check for complex nested structure
        if ResponseFormatter._is_complex_structure(data):
            logger.info("Using hybrid format: complex structure")
            return True
        
        return False
    
    @staticmethod
    def _is_complex_structure(data: Dict[str, Any]) -> bool:
        """
        Check if data has complex nested structure.
        
        Args:
            data: Data dict to evaluate
        
        Returns:
            True if structure is complex
        """
        if not isinstance(data, dict):
            return False
        
        # Count nesting levels
        def count_nesting(obj, level=0):
            if level > ResponseFormatter.HYBRID_THRESHOLD_COMPLEXITY:
                return level
            
            if isinstance(obj, dict):
                if not obj:
                    return level
                return max(
                    count_nesting(v, level + 1) 
                    for v in obj.values()
                )
            elif isinstance(obj, list):
                if not obj:
                    return level
                return max(
                    count_nesting(item, level + 1) 
                    for item in obj
                )
            else:
                return level
        
        nesting_level = count_nesting(data)
        return nesting_level > 3


class ResponseValidator:
    """Validator for API responses"""
    
    @staticmethod
    def validate(response: Dict[str, Any]) -> bool:
        """
        Validate response structure.
        
        Args:
            response: Response dict to validate
        
        Returns:
            True if valid
        
        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        required_fields = ['answer', 'data', 'agent_used']
        for field in required_fields:
            if field not in response:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate answer
        if not isinstance(response['answer'], str):
            raise ValueError("'answer' must be a string")
        
        if not response['answer'].strip():
            raise ValueError("'answer' cannot be empty")
        
        # Validate data (can be None or dict)
        if response['data'] is not None:
            if not isinstance(response['data'], dict):
                raise ValueError("'data' must be a dict or None")
        
        # Validate agent_used
        valid_agents = ['analytics', 'seo', 'multi-agent', 'unknown']
        if response['agent_used'] not in valid_agents:
            logger.warning(
                f"Unexpected agent_used value: {response['agent_used']}"
            )
        
        return True


class DataFormatter:
    """Utility for formatting data payloads"""
    
    @staticmethod
    def format_rows(
        rows: list,
        row_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Format rows with metadata.
        
        Args:
            rows: List of data rows
            row_limit: Optional limit on rows returned
        
        Returns:
            Formatted data dict
        """
        if row_limit and len(rows) > row_limit:
            rows = rows[:row_limit]
            truncated = True
        else:
            truncated = False
        
        result = {
            "rows": rows,
            "row_count": len(rows)
        }
        
        if truncated:
            result["truncated"] = True
            result["note"] = f"Results limited to {row_limit} rows"
        
        return result
    
    @staticmethod
    def add_summary(
        data: Dict[str, Any],
        summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Add summary statistics to data.
        
        Args:
            data: Original data dict
            summary: Summary statistics dict
        
        Returns:
            Data with summary added
        """
        data_copy = data.copy()
        data_copy['summary'] = summary
        return data_copy
    
    @staticmethod
    def format_error_response(
        error_message: str,
        error_type: str = "Unknown"
    ) -> Dict[str, Any]:
        """
        Format error as response.
        
        Args:
            error_message: Error description
            error_type: Error category
        
        Returns:
            Error response dict
        """
        return {
            "answer": f"Error processing query: {error_message}",
            "data": {
                "error": error_type,
                "message": error_message
            },
            "agent_used": "error_handler"
        }