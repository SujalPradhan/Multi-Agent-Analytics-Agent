"""
Orchestrator - Multi-Agent Coordination

This is the brain of the system. It:
1. Detects query intent (Analytics/SEO/Multi)
2. Detects response format preference (NL/JSON)
3. Routes to appropriate agent(s)
4. Decomposes complex multi-agent tasks
5. Aggregates results
6. Returns unified response

The orchestrator uses LLM for intelligent routing and task decomposition.
"""

import logging
import os
from typing import Dict, Any, Optional, List
import asyncio

from llm_client import LLMClient, LLMPromptBuilder

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Multi-agent orchestrator.
    
    Routes queries to appropriate agents and coordinates responses.
    """
    
    # Intent types
    INTENT_ANALYTICS = "analytics"
    INTENT_SEO = "seo"
    INTENT_MULTI = "multi-agent"
    
    def __init__(
        self,
        litellm_api_key: str,
        credentials_path: str,
        default_sheet_id: Optional[str] = None,
        default_property_id: Optional[str] = None
    ):
        """
        Initialize orchestrator.
        
        Args:
            litellm_api_key: LiteLLM API key
            credentials_path: Path to Google credentials JSON
            default_sheet_id: Default Google Sheets ID for SEO data
            default_property_id: Default GA4 property ID
        """
        self.llm_client = LLMClient(api_key=litellm_api_key)
        self.credentials_path = credentials_path
        self.default_sheet_id = default_sheet_id
        self.default_property_id = default_property_id
        
        # Initialize agents (lazy loading)
        self.analytics_agent = None
        self.seo_agent = None
        
        logger.info("Orchestrator initialized")
        logger.info(f"Default Sheet ID: {default_sheet_id or 'Not set'}")
        logger.info(f"Default Property ID: {default_property_id or 'Not set'}")
    
    def _init_analytics_agent(self):
        """Lazy initialization of analytics agent"""
        if self.analytics_agent is None:
            from analytics_agent import AnalyticsAgent
            self.analytics_agent = AnalyticsAgent(
                llm_client=self.llm_client,
                credentials_path=self.credentials_path,
                default_property_id=self.default_property_id
            )
            logger.info("✓ Analytics agent initialized")
    
    def _init_seo_agent(self):
        """Lazy initialization of SEO agent"""
        if self.seo_agent is None:
            from seo_agent import SEOAgent
            from sheets_client import SheetsClient
            
            # Initialize Sheets client for SEO data access
            sheets_client = SheetsClient(credentials_path=self.credentials_path)
            
            self.seo_agent = SEOAgent(
                llm_client=self.llm_client,
                sheets_client=sheets_client,
                default_sheet_id=self.default_sheet_id
            )
            logger.info("✓ SEO agent initialized")
    
    async def process_query(
        self,
        query: str,
        property_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for query processing.
        
        Args:
            query: Natural language query
            property_id: GA4 property ID (optional)
        
        Returns:
            Dict with 'answer', 'data', and 'agent_used'
        """
        logger.info("=" * 70)
        logger.info("ORCHESTRATOR: Processing query")
        logger.info(f"Query: {query}")
        logger.info("=" * 70)
        
        try:
            # Step 1: Detect JSON request preference
            json_requested = self._detect_json_request(query)
            logger.info(f"JSON requested: {json_requested}")
            
            # Step 2: Detect intent
            intent = await self._detect_intent(query)
            logger.info(f"Intent detected: {intent}")
            
            # Step 3: Route to agent(s)
            if intent == self.INTENT_ANALYTICS:
                result = await self._route_to_analytics(
                    query, 
                    property_id, 
                    json_requested
                )
            
            elif intent == self.INTENT_SEO:
                result = await self._route_to_seo(
                    query, 
                    json_requested
                )
            
            elif intent == self.INTENT_MULTI:
                result = await self._route_to_multi_agent(
                    query, 
                    property_id, 
                    json_requested
                )
            
            else:
                raise ValueError(f"Unknown intent: {intent}")
            
            logger.info("ORCHESTRATOR: Query processing complete")
            logger.info("=" * 70)
            
            return result
        
        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            raise
    
    def _detect_json_request(self, query: str) -> bool:
        """
        Detect if user explicitly requests JSON format.
        
        Keywords: "json", "JSON", "json format", "return as json",
                  "give me json", "output json", etc.
        
        Args:
            query: User query
        
        Returns:
            True if JSON format requested
        """
        query_lower = query.lower()
        
        json_keywords = [
            "json",
            "json format",
            "return as json",
            "give me json",
            "output json",
            "in json",
            "as json",
            "return json",
            "format json",
            "structured data"
        ]
        
        detected = any(keyword in query_lower for keyword in json_keywords)
        
        if detected:
            logger.info(f"JSON format detected in query")
        
        return detected
    
    async def _detect_intent(self, query: str) -> str:
        """
        Detect query intent using LLM.
        
        Classifies into:
        - analytics: GA4 data (users, sessions, pageviews, etc.)
        - seo: SEO data (meta descriptions, URLs, redirects, etc.)
        - multi-agent: Requires both data sources
        
        Args:
            query: User query
        
        Returns:
            Intent string (analytics/seo/multi-agent)
        """
        prompt = f"""Analyze this query and classify its intent.

Query: "{query}"

Classification options:
1. "analytics" - Query about website analytics data:
   - User metrics (users, sessions, pageviews)
   - Traffic sources
   - Device categories
   - Page performance
   - Conversion metrics
   - Time-based trends
   
2. "seo" - Query about SEO/technical data:
   - Meta descriptions
   - Page titles
   - URL structure
   - Redirects
   - Broken links
   - Indexability
   - Technical SEO issues
   
3. "multi-agent" - Query requires BOTH data sources:
   - Combining traffic data with SEO issues
   - Analyzing high-traffic pages with SEO problems
   - Correlating performance with technical issues

Respond with ONLY the classification: "analytics", "seo", or "multi-agent"
"""
        
        messages = [
            LLMPromptBuilder.build_system_message(
                "an expert at classifying analytics and SEO queries"
            ),
            LLMPromptBuilder.build_user_message(prompt)
        ]
        
        response = self.llm_client.chat(
            messages=messages,
            model='flash',
            temperature=0.1
        )
        
        # Parse response
        intent = response.strip().lower()
        
        # Validate
        if intent not in [self.INTENT_ANALYTICS, self.INTENT_SEO, self.INTENT_MULTI]:
            logger.warning(f"Invalid intent '{intent}', defaulting to analytics")
            intent = self.INTENT_ANALYTICS
        
        return intent
    
    async def _route_to_analytics(
        self,
        query: str,
        property_id: Optional[str],
        json_requested: bool
    ) -> Dict[str, Any]:
        """
        Route query to analytics agent.
        
        Args:
            query: User query
            property_id: GA4 property ID
            json_requested: JSON format flag
        
        Returns:
            Agent response dict
        """
        logger.info("Routing to Analytics Agent")
        
        self._init_analytics_agent()
        
        if self.analytics_agent is None:
            raise NotImplementedError(
                "Analytics agent is not yet implemented. "
                "Please implement the analytics_agent module."
            )
        
        result = await self.analytics_agent.process(
            query=query,
            property_id=property_id or self.default_property_id,
            json_requested=json_requested
        )
        
        result['agent_used'] = self.INTENT_ANALYTICS
        return result
    
    async def _route_to_seo(
        self,
        query: str,
        json_requested: bool
    ) -> Dict[str, Any]:
        """
        Route query to SEO agent.
        
        Args:
            query: User query
            json_requested: JSON format flag
        
        Returns:
            Agent response dict
        """
        logger.info("Routing to SEO Agent")
        
        self._init_seo_agent()
        
        if self.seo_agent is None:
            raise NotImplementedError(
                "SEO agent is not yet implemented. "
                "Please implement the seo_agent module."
            )
        
        result = await self.seo_agent.process(
            query=query,
            json_requested=json_requested
        )
        
        result['agent_used'] = self.INTENT_SEO
        return result
    
    async def _route_to_multi_agent(
        self,
        query: str,
        property_id: Optional[str],
        json_requested: bool
    ) -> Dict[str, Any]:
        """
        Route query to multiple agents and aggregate results.
        
        Process:
        1. Decompose query into sub-tasks
        2. Route sub-tasks to appropriate agents
        3. Execute in parallel
        4. Aggregate results
        5. Synthesize final answer
        
        Args:
            query: User query
            property_id: GA4 property ID
            json_requested: JSON format flag
        
        Returns:
            Aggregated response dict
        """
        logger.info("Routing to Multi-Agent pipeline")
        
        # Initialize both agents
        self._init_analytics_agent()
        self._init_seo_agent()
        
        # Decompose query into sub-tasks
        tasks = await self._decompose_query(query)
        logger.info(f"Decomposed into {len(tasks)} tasks")
        
        # Execute tasks in parallel
        results = await self._execute_tasks_parallel(
            tasks, 
            property_id, 
            json_requested
        )
        
        # Aggregate results
        aggregated = await self._aggregate_results(
            query,
            results,
            json_requested
        )
        
        aggregated['agent_used'] = self.INTENT_MULTI
        return aggregated
    
    async def _decompose_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Decompose complex query into sub-tasks.
        
        Args:
            query: Original query
        
        Returns:
            List of task dicts with 'agent' and 'sub_query'
        """
        prompt = f"""Decompose this query into specific sub-tasks for analytics and SEO agents.

Query: "{query}"

Break it down into:
1. Analytics tasks (GA4 data needed)
2. SEO tasks (SEO data needed)

Format as JSON array:
[
  {{"agent": "analytics", "sub_query": "specific analytics question"}},
  {{"agent": "seo", "sub_query": "specific SEO question"}}
]

Keep sub-queries focused and specific.
"""
        
        messages = [
            LLMPromptBuilder.build_system_message(
                "a task decomposition expert"
            ),
            LLMPromptBuilder.build_user_message(prompt)
        ]
        
        tasks = self.llm_client.chat(
            messages=messages,
            model='flash',
            temperature=0.2,
            json_mode=True
        )
        
        if not isinstance(tasks, list):
            logger.warning("Task decomposition did not return list, using original query")
            return [
                {"agent": "analytics", "sub_query": query},
                {"agent": "seo", "sub_query": query}
            ]
        
        return tasks
    
    async def _execute_tasks_parallel(
        self,
        tasks: List[Dict[str, Any]],
        property_id: Optional[str],
        json_requested: bool
    ) -> List[Dict[str, Any]]:
        """
        Execute tasks in parallel.
        
        Args:
            tasks: List of task dicts
            property_id: GA4 property ID
            json_requested: JSON format flag
        
        Returns:
            List of result dicts
        """
        async def execute_task(task):
            agent_type = task.get('agent')
            sub_query = task.get('sub_query')
            
            if agent_type == 'analytics':
                return await self._route_to_analytics(
                    sub_query, 
                    property_id, 
                    json_requested
                )
            elif agent_type == 'seo':
                return await self._route_to_seo(
                    sub_query, 
                    json_requested
                )
            else:
                logger.warning(f"Unknown agent type: {agent_type}")
                return None
        
        # Execute all tasks concurrently
        results = await asyncio.gather(
            *[execute_task(task) for task in tasks],
            return_exceptions=True
        )
        
        # Filter out exceptions
        valid_results = [
            r for r in results 
            if r is not None and not isinstance(r, Exception)
        ]
        
        return valid_results
    
    async def _aggregate_results(
        self,
        original_query: str,
        results: List[Dict[str, Any]],
        json_requested: bool
    ) -> Dict[str, Any]:
        """
        Aggregate results from multiple agents.
        
        Args:
            original_query: Original user query
            results: List of agent results
            json_requested: JSON format flag
        
        Returns:
            Unified response dict
        """
        if not results:
            return {
                "answer": "Unable to process query with available agents.",
                "data": None
            }
        
        # Extract data and answers from results
        all_data = {}
        all_answers = []
        
        for i, result in enumerate(results):
            if result.get('answer'):
                all_answers.append(result['answer'])
            if result.get('data'):
                all_data[f"source_{i+1}"] = result['data']
        
        # Synthesize unified answer using LLM
        if json_requested:
            # Return combined data in JSON format
            return {
                "answer": "Combined results from analytics and SEO data returned in JSON format",
                "data": all_data if all_data else None
            }
        else:
            # Synthesize narrative answer
            synthesis_prompt = f"""Synthesize these results into a unified answer.

Original Query: "{original_query}"

Agent Results:
{chr(10).join([f"{i+1}. {ans}" for i, ans in enumerate(all_answers)])}

Create a cohesive, insightful answer that:
1. Addresses the original query
2. Combines insights from both data sources
3. Highlights key findings
4. Provides actionable recommendations if applicable

Keep it concise but comprehensive."""
            
            messages = [
                LLMPromptBuilder.build_system_message(
                    "an expert at synthesizing multi-source analytics insights"
                ),
                LLMPromptBuilder.build_user_message(synthesis_prompt)
            ]
            
            unified_answer = self.llm_client.chat(
                messages=messages,
                model='flash',
                temperature=0.4
            )
            
            # Decide if we should include data (hybrid mode)
            include_data = len(all_data) > 0 and self._should_use_hybrid(all_data)
            
            return {
                "answer": unified_answer,
                "data": all_data if include_data else None
            }
    
    def _should_use_hybrid(self, data: Dict[str, Any]) -> bool:
        """
        Determine if response should be hybrid (NL + data).
        
        Args:
            data: Data dict
        
        Returns:
            True if hybrid mode appropriate
        """
        if not data:
            return False
        
        # Use hybrid if data is substantial
        total_rows = 0
        for source_data in data.values():
            if isinstance(source_data, dict) and 'rows' in source_data:
                total_rows += len(source_data.get('rows', []))
        
        return total_rows > 5
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics"""
        return {
            "token_usage": self.llm_client.get_usage(),
            "cost_estimate": self.llm_client.estimate_cost()
        }
    
    def log_usage(self):
        """Log usage statistics"""
        self.llm_client.log_usage()
        
        cost_estimate = self.llm_client.estimate_cost()
        logger.info("COST ESTIMATE")
        logger.info(f"Estimated cost: ${cost_estimate['total_cost']:.4f}")
        logger.info(f"Budget remaining: ${cost_estimate['budget_remaining']:.2f}")