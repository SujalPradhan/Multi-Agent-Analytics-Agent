"""
API Gateway - FastAPI Server

This is the main entry point for the Multi-Agent Analytics System.
Handles HTTP requests, validation, and response formatting.

Port: 8080 (CRITICAL - must not change)
Endpoint: POST /query

OpenAI API Configuration (via AI Pipe):
- Base URL: https://aipipe.org/openai/v1
- Model: gpt-4o-mini
- Uses OpenAI-compatible SDK
- API Key from OPENAI_API_KEY env variable (AI Pipe Token)
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, Field
from typing import Optional, Any, Dict
import uvicorn
import logging
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from orchestrator import Orchestrator

# Configure logging
log_handlers = [logging.StreamHandler()]

# Only add file handler in local dev (not on HF Spaces)
if os.getenv("SPACE_ID") is None:
    try:
        log_handlers.append(logging.FileHandler('api.log'))
    except (PermissionError, OSError):
        pass  # Skip file logging if not writable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Spike AI Multi-Agent Analytics API",
    version="1.0.0",
    description="Natural language interface for GA4 and SEO data analysis"
)

# Global orchestrator instance
orchestrator = None


class QueryRequest(BaseModel):
    """Request schema for /query endpoint"""
    query: str = Field(
        ..., 
        min_length=1, 
        max_length=1000,
        description="Natural language query about analytics or SEO data"
    )
    propertyId: Optional[str] = Field(
        None,
        description="GA4 property ID (optional if set in environment)"
    )
    
    @validator('query')
    def query_not_empty(cls, v):
        """Ensure query is not just whitespace"""
        if not v or v.strip() == "":
            raise ValueError('Query cannot be empty or whitespace')
        return v.strip()
    
    @validator('propertyId')
    def validate_property_id(cls, v):
        """Validate propertyId format if provided"""
        if v is not None:
            v = v.strip()
            if not v.isdigit():
                raise ValueError('propertyId must be numeric')
        return v


class QueryResponse(BaseModel):
    """Response schema for /query endpoint"""
    answer: str = Field(
        ..., 
        description="Natural language answer or JSON confirmation"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured data (present in JSON or Hybrid modes)"
    )
    agent_used: str = Field(
        ...,
        description="Which agent(s) processed the query"
    )


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    detail: str
    timestamp: str


@app.on_event("startup")
async def startup_event():
    """Initialize orchestrator on server startup"""
    global orchestrator
    
    logger.info("=" * 70)
    logger.info("Starting Spike AI Multi-Agent Analytics API")
    logger.info("=" * 70)
    
    try:
        # Load environment variables
        openai_api_key = os.getenv('OPENAI_API_KEY')
        sheet_id = os.getenv('SHEET_ID')
        property_id = os.getenv('GA4_PROPERTY_ID')
        credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        
        # Validate critical environment variables
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")
        
        if not os.path.exists(credentials_path):
            raise ValueError(f"Credentials file not found: {credentials_path}")
        
        logger.info(f"Credentials path: {credentials_path}")
        logger.info(f"Sheet ID configured: {sheet_id is not None}")
        logger.info(f"GA4 Property ID configured: {property_id is not None}")
        
        # Initialize orchestrator
        orchestrator = Orchestrator(
            litellm_api_key=openai_api_key,
            credentials_path=credentials_path,
            default_sheet_id=sheet_id,
            default_property_id=property_id
        )
        
        logger.info("✓ Orchestrator initialized successfully")
        logger.info("✓ API Gateway ready to accept requests")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {e}", exc_info=True)
        raise


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "service": "Spike AI Multi-Agent Analytics API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "query": "POST /query",
            "health": "GET /health"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    if orchestrator is None:
        raise HTTPException(
            status_code=503, 
            detail="Orchestrator not initialized"
        )
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "orchestrator": "initialized",
        "agents": {
            "analytics": orchestrator.analytics_agent is not None,
            "seo": orchestrator.seo_agent is not None
        }
    }


@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process natural language queries about analytics and SEO data.
    
    This is the main endpoint that:
    1. Validates the request
    2. Routes to the orchestrator
    3. Returns formatted response (NL/JSON/Hybrid)
    
    Request Format:
    {
        "query": "What are my top pages this week?",
        "propertyId": "123456789"  // Optional
    }
    
    Response Format:
    {
        "answer": "Natural language explanation or JSON confirmation",
        "data": {...},  // Optional structured data
        "agent_used": "analytics|seo|multi-agent"
    }
    """
    start_time = datetime.utcnow()
    
    logger.info("=" * 70)
    logger.info(f"NEW REQUEST")
    logger.info(f"Query: {request.query}")
    logger.info(f"PropertyId: {request.propertyId or 'Not provided'}")
    logger.info("=" * 70)
    
    try:
        # Check if orchestrator is initialized
        if orchestrator is None:
            raise HTTPException(
                status_code=503,
                detail="Service not ready. Orchestrator not initialized."
            )
        
        # Process query through orchestrator
        result = await orchestrator.process_query(
            query=request.query,
            property_id=request.propertyId
        )
        
        # Calculate processing time
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info("=" * 70)
        logger.info(f"REQUEST COMPLETED")
        logger.info(f"Agent Used: {result['agent_used']}")
        logger.info(f"Processing Time: {processing_time:.2f}s")
        logger.info(f"Has Data: {result.get('data') is not None}")
        logger.info("=" * 70)
        
        return JSONResponse(
            content=result,
            status_code=200
        )
        
    except ValueError as e:
        # User input validation errors
        logger.warning(f"Validation error: {e}")
        error_response = ErrorResponse(
            error="Validation Error",
            detail=str(e),
            timestamp=datetime.utcnow().isoformat()
        )
        raise HTTPException(status_code=400, detail=error_response.dict())
    
    except TimeoutError as e:
        # Query processing timeout
        logger.error(f"Timeout error: {e}")
        error_response = ErrorResponse(
            error="Timeout",
            detail="Query processing exceeded timeout limit",
            timestamp=datetime.utcnow().isoformat()
        )
        raise HTTPException(status_code=504, detail=error_response.dict())
    
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error: {e}", exc_info=True)
        error_response = ErrorResponse(
            error="Internal Server Error",
            detail="An unexpected error occurred while processing your query",
            timestamp=datetime.utcnow().isoformat()
        )
        raise HTTPException(status_code=500, detail=error_response.dict())


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for uncaught exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def run_server():
    """Run the FastAPI server"""
    # Get configuration from environment
    # Use 0.0.0.0 for container/cloud deployments
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 7860))
    
    logger.info(f"Starting server on http://{host}:{port}")
    logger.info(f"Documentation available at http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )

#run
if __name__ == "__main__":
    run_server()