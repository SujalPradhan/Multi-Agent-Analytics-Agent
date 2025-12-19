"""
LLM Client - LiteLLM Proxy Interface

Handles all interactions with the LiteLLM proxy server.

LiteLLM Proxy Details:
- Base URL: http://3.110.18.218
- API Key Format: sk-... (provided via email)
- Compatible with OpenAI SDK

Available Models (from api.md):
- gemini-2.5-flash: Fast, cheap, for most queries
- gemini-2.5-pro: Complex reasoning, use sparingly  
- gemini-3-pro-preview: Latest preview model

Features:
- Exponential backoff for rate limiting (429 errors)
- Token usage tracking
- JSON mode support
- Model selection (flash vs pro)
- Error handling and retries

Budget: $100 LiteLLM credits (must be monitored)
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional, Union
from openai import OpenAI, APIError, RateLimitError, APITimeoutError

logger = logging.getLogger(__name__)


# LiteLLM Proxy Configuration
LITELLM_BASE_URL = "http://3.110.18.218"


class LLMClient:
    """
    Client for interacting with LiteLLM proxy.
    
    Uses OpenAI-compatible API pointing to LiteLLM proxy.
    The proxy routes requests to Google Gemini models.
    
    Available models (per api.md):
    - gemini-2.5-flash: Fast, cheap, for most queries
    - gemini-2.5-pro: Complex reasoning, use sparingly
    - gemini-3-pro-preview: Latest preview model
    """
    
    # Model configurations - mapped to friendly names
    # These are the actual model names to send to LiteLLM
    MODELS = {
        'flash': 'gemini-2.5-flash',      # Fast, cheap - use for most queries
        'pro': 'gemini-2.5-pro',          # Complex reasoning - use sparingly
        'preview': 'gemini-3-pro-preview' # Latest preview model
    }
    
    # Retry configuration for handling 429 rate limits
    MAX_RETRIES = 5
    BASE_DELAY = 1  # seconds - will exponentially increase: 1s, 2s, 4s, 8s, 16s
    MAX_DELAY = 16  # seconds
    TIMEOUT = 60.0  # seconds
    
    def __init__(self, api_key: str, base_url: str = LITELLM_BASE_URL):
        """
        Initialize LLM client.
        
        Args:
            api_key: LiteLLM API key (format: sk-...)
            base_url: LiteLLM proxy URL (default: http://3.110.18.218)
        
        Note:
            Uses OpenAI SDK pointed at LiteLLM proxy which routes
            to Google Gemini models. Do NOT use googleapis.com directly.
        """
        self.api_key = api_key
        self.base_url = base_url
        
        # Initialize OpenAI client pointing to LiteLLM proxy
        # This is the recommended approach per api.md
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.TIMEOUT
        )
        
        # Token usage tracking
        self.token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "requests": 0
        }
        
        logger.info(f"LLM Client initialized with base_url: {base_url}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = 'preview',
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Send chat completion request with exponential backoff retry.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: 'flash' or 'pro' (maps to actual model names)
            temperature: 0.0-1.0, lower = more deterministic
            max_tokens: Maximum tokens in response
            json_mode: Force JSON response format
        
        Returns:
            str: Response content (normal mode)
            dict: Parsed JSON (json_mode=True)
        
        Raises:
            ValueError: If JSON parsing fails in json_mode
            APIError: If API request fails after retries
        """
        # Get actual model name
        model_name = self.MODELS.get(model, self.MODELS['flash'])
        
        # Add JSON instruction if needed
        if json_mode:
            messages = self._add_json_instruction(messages)
        
        logger.info(f"LLM Request: model={model_name}, json_mode={json_mode}, messages={len(messages)}")
        
        # Retry loop with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                # Prepare request kwargs
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature
                }
                
                if max_tokens:
                    kwargs["max_tokens"] = max_tokens
                
                # Make API call
                response = self.client.chat.completions.create(**kwargs)
                
                # Track token usage
                self._update_usage(response)
                
                # Extract content
                content = response.choices[0].message.content
                
                logger.info(f"LLM Response received: {len(content)} chars")
                
                # Parse JSON if requested
                if json_mode:
                    return self._parse_json_response(content)
                
                return content
            
            except RateLimitError as e:
                # Handle rate limiting with exponential backoff
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = min(
                        self.BASE_DELAY * (2 ** attempt),
                        self.MAX_DELAY
                    )
                    logger.warning(
                        f"Rate limited (429). Retry {attempt+1}/{self.MAX_RETRIES} "
                        f"in {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded for rate limiting")
                    raise
            
            except APITimeoutError as e:
                logger.error(f"Request timeout: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    logger.info(f"Retrying... ({attempt+1}/{self.MAX_RETRIES})")
                    time.sleep(self.BASE_DELAY)
                else:
                    raise
            
            except APIError as e:
                logger.error(f"API Error: {e}")
                if attempt < self.MAX_RETRIES - 1 and e.status_code >= 500:
                    # Retry on server errors
                    wait_time = self.BASE_DELAY * (2 ** attempt)
                    logger.info(f"Retrying after server error in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    raise
            
            except Exception as e:
                logger.error(f"Unexpected error in LLM call: {e}", exc_info=True)
                raise
        
        raise Exception("Max retries exceeded")
    
    def _add_json_instruction(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Add JSON formatting instruction to messages.
        
        Args:
            messages: Original message list
        
        Returns:
            Modified message list with JSON instruction
        """
        messages = messages.copy()
        
        # Add instruction to last user message
        if messages and messages[-1]['role'] == 'user':
            messages[-1]['content'] += (
                "\n\nIMPORTANT: Respond with ONLY valid JSON. "
                "No markdown, no explanations, just the JSON object."
            )
        
        return messages
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON response, handling markdown fences.
        
        Args:
            content: Raw response content
        
        Returns:
            Parsed JSON dict
        
        Raises:
            ValueError: If JSON parsing fails
        """
        # Strip whitespace
        content = content.strip()
        
        # Remove markdown code fences if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Raw content: {content[:500]}...")
            raise ValueError(
                f"LLM did not return valid JSON. Parse error: {e}"
            )
    
    def _update_usage(self, response):
        """
        Update token usage statistics.
        
        Args:
            response: OpenAI API response object
        """
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            self.token_usage["input_tokens"] += usage.prompt_tokens
            self.token_usage["output_tokens"] += usage.completion_tokens
            self.token_usage["total_tokens"] += usage.total_tokens
            self.token_usage["requests"] += 1
            
            logger.debug(
                f"Token usage: +{usage.prompt_tokens} input, "
                f"+{usage.completion_tokens} output"
            )
    
    def get_usage(self) -> Dict[str, int]:
        """
        Get token usage statistics.
        
        Returns:
            Dict with token usage breakdown
        """
        return self.token_usage.copy()
    
    def log_usage(self):
        """Log current token usage"""
        usage = self.get_usage()
        logger.info("=" * 70)
        logger.info("LLM USAGE STATISTICS")
        logger.info(f"Total Requests: {usage['requests']}")
        logger.info(f"Input Tokens: {usage['input_tokens']:,}")
        logger.info(f"Output Tokens: {usage['output_tokens']:,}")
        logger.info(f"Total Tokens: {usage['total_tokens']:,}")
        logger.info("=" * 70)
    
    def estimate_cost(self) -> Dict[str, float]:
        """
        Estimate cost based on token usage.
        
        Note: These are rough estimates. Actual pricing depends on model.
        Gemini Flash: ~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens
        Gemini Pro: ~$1.25 per 1M input tokens, ~$5.00 per 1M output tokens
        
        Returns:
            Dict with cost estimates
        """
        usage = self.get_usage()
        
        # Rough estimates (assuming mostly flash)
        input_cost = (usage['input_tokens'] / 1_000_000) * 0.075
        output_cost = (usage['output_tokens'] / 1_000_000) * 0.30
        total_cost = input_cost + output_cost
        
        return {
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "budget_remaining": 100.0 - total_cost
        }


class LLMPromptBuilder:
    """Helper class for building consistent prompts"""
    
    @staticmethod
    def build_system_message(role: str, context: str = "") -> Dict[str, str]:
        """
        Build system message for agent.
        
        Args:
            role: Agent role description
            context: Additional context
        
        Returns:
            System message dict
        """
        content = f"You are {role}."
        if context:
            content += f"\n\n{context}"
        
        return {"role": "system", "content": content}
    
    @staticmethod
    def build_user_message(query: str, data: Optional[str] = None) -> Dict[str, str]:
        """
        Build user message.
        
        Args:
            query: User query
            data: Additional data context
        
        Returns:
            User message dict
        """
        content = query
        if data:
            content += f"\n\nData:\n{data}"
        
        return {"role": "user", "content": content}
    
    @staticmethod
    def build_assistant_message(content: str) -> Dict[str, str]:
        """Build assistant message"""
        return {"role": "assistant", "content": content}