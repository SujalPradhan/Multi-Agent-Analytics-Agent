"""
Google Sheets Client - SEO Data Source

SEO DATA SOURCE GUARANTEE:
- Primary source: Google Sheets API (Screaming Frog export)
- Caching: In-memory only, session-scoped
- NO static CSVs or local files permitted
- Fetches fresh data every session start

Features:
- Service account authentication from credentials.json
- Session-scoped in-memory caching (sheet-level)
- Auto-detect tab: "Internal" first, fallback to first worksheet
- Dynamic column header detection
- Graceful error handling for API failures
"""

import logging
from typing import Dict, Any, Optional, List
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


class SheetsClientError(Exception):
    """Base exception for Sheets client errors"""
    pass


class SheetsAuthenticationError(SheetsClientError):
    """Authentication failed with credentials"""
    pass


class SheetsNotFoundError(SheetsClientError):
    """Sheet or worksheet not found"""
    pass


class SheetsAPIError(SheetsClientError):
    """Google Sheets API call failed"""
    pass


class SheetsClient:
    """
    Google Sheets client for SEO data access.
    
    Handles authentication, sheet fetching, and in-memory caching.
    All data is fetched from Google Sheets API - no local files.
    
    SEO DATA SOURCE GUARANTEE:
    - Primary source: Google Sheets API (Screaming Frog export)
    - Caching: In-memory only, session-scoped
    - NO static CSVs or local files permitted
    - Fetches fresh data every session start
    """
    
    # Google Sheets API scopes
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
        'https://www.googleapis.com/auth/drive.readonly'
    ]
    
    # Default tab names to try (Screaming Frog standard exports)
    DEFAULT_TAB_NAMES = ['Internal', 'All', 'internal', 'Sheet1']
    
    def __init__(self, credentials_path: str):
        """
        Initialize Sheets client with service account credentials.
        
        Args:
            credentials_path: Path to credentials.json file
            
        Note:
            Does NOT connect automatically. Call connect() to authenticate.
        """
        self.credentials_path = credentials_path
        self.client: Optional[gspread.Client] = None
        
        # In-memory cache: session-scoped, sheet-level
        # Structure: {sheet_id: {'df': DataFrame, 'columns': List[str]}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("SheetsClient initialized (not yet connected)")
    
    def connect(self) -> None:
        """
        Establish connection to Google Sheets API.
        
        Raises:
            SheetsAuthenticationError: If credentials are invalid
        """
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.SCOPES
            )
            self.client = gspread.authorize(credentials)
            logger.info("✓ Connected to Google Sheets API")
        except FileNotFoundError:
            raise SheetsAuthenticationError(
                f"Credentials file not found: {self.credentials_path}. "
                "Please ensure credentials.json exists at the project root."
            )
        except Exception as e:
            raise SheetsAuthenticationError(
                f"Failed to authenticate with Google Sheets: {str(e)}"
            )
    
    def _ensure_connected(self) -> None:
        """Ensure client is connected, connect if not."""
        if self.client is None:
            self.connect()
    
    def _find_worksheet(self, spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
        """
        Find the best worksheet to use.
        
        Priority:
        1. "Internal" tab (standard Screaming Frog export)
        2. First tab in DEFAULT_TAB_NAMES that exists
        3. First available worksheet
        
        Args:
            spreadsheet: gspread Spreadsheet object
            
        Returns:
            gspread Worksheet object
            
        Raises:
            SheetsNotFoundError: If no worksheets found
        """
        worksheet_titles = [ws.title for ws in spreadsheet.worksheets()]
        
        if not worksheet_titles:
            raise SheetsNotFoundError("Spreadsheet has no worksheets")
        
        # Try default tab names first
        for tab_name in self.DEFAULT_TAB_NAMES:
            if tab_name in worksheet_titles:
                logger.info(f"Using worksheet: '{tab_name}'")
                return spreadsheet.worksheet(tab_name)
        
        # Fallback to first worksheet
        first_worksheet = spreadsheet.worksheets()[0]
        logger.info(f"Using first worksheet: '{first_worksheet.title}'")
        return first_worksheet
    
    def fetch_sheet(self, sheet_id: str, force_refresh: bool = False) -> pd.DataFrame:
        """
        Fetch sheet data from Google Sheets API.
        
        Uses in-memory cache if available (session-scoped).
        No disk persistence - all data comes from API.
        
        Args:
            sheet_id: Google Sheets ID
            force_refresh: Force API fetch even if cached
            
        Returns:
            pandas DataFrame with sheet data
            
        Raises:
            SheetsNotFoundError: If sheet doesn't exist or no access
            SheetsAPIError: If API call fails
        """
        self._ensure_connected()
        
        # Check cache (in-memory only)
        if not force_refresh and sheet_id in self._cache:
            logger.info(f"Using cached data for sheet: {sheet_id}")
            return self._cache[sheet_id]['df'].copy()
        
        # Fetch from API
        logger.info(f"Fetching sheet from API: {sheet_id}")
        
        try:
            spreadsheet = self.client.open_by_key(sheet_id)
            worksheet = self._find_worksheet(spreadsheet)
            
            # Get all values including headers
            all_values = worksheet.get_all_values()
            
            if not all_values:
                logger.warning(f"Sheet is empty: {sheet_id}")
                df = pd.DataFrame()
                self._cache[sheet_id] = {'df': df, 'columns': []}
                return df
            
            # First row is headers
            headers = all_values[0]
            data = all_values[1:] if len(all_values) > 1 else []
            
            # Create DataFrame
            df = pd.DataFrame(data, columns=headers)
            
            # Clean up empty columns
            df = df.loc[:, df.columns.str.strip() != '']
            
            # Store in cache (in-memory only, session-scoped)
            self._cache[sheet_id] = {
                'df': df,
                'columns': list(df.columns)
            }
            
            logger.info(f"✓ Fetched {len(df)} rows, {len(df.columns)} columns")
            logger.info(f"Columns: {list(df.columns)[:10]}{'...' if len(df.columns) > 10 else ''}")
            
            return df.copy()
            
        except gspread.exceptions.SpreadsheetNotFound:
            raise SheetsNotFoundError(
                f"Spreadsheet not found: {sheet_id}. "
                "Please verify the Sheet ID and ensure the service account has access."
            )
        except gspread.exceptions.APIError as e:
            raise SheetsAPIError(
                f"Google Sheets API error: {str(e)}"
            )
        except Exception as e:
            raise SheetsAPIError(
                f"Failed to fetch sheet data: {str(e)}"
            )
    
    def get_columns(self, sheet_id: str) -> List[str]:
        """
        Get column headers for a sheet.
        
        Fetches from cache if available, otherwise triggers API fetch.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            List of column header names
        """
        # Ensure data is fetched
        if sheet_id not in self._cache:
            self.fetch_sheet(sheet_id)
        
        return self._cache[sheet_id]['columns'].copy()
    
    def is_cached(self, sheet_id: str) -> bool:
        """
        Check if sheet data is in cache.
        
        Args:
            sheet_id: Google Sheets ID
            
        Returns:
            True if cached, False otherwise
        """
        return sheet_id in self._cache
    
    def clear_cache(self, sheet_id: Optional[str] = None) -> None:
        """
        Clear in-memory cache.
        
        Args:
            sheet_id: Specific sheet to clear, or None to clear all
        """
        if sheet_id:
            if sheet_id in self._cache:
                del self._cache[sheet_id]
                logger.info(f"Cleared cache for sheet: {sheet_id}")
        else:
            self._cache.clear()
            logger.info("Cleared all sheet cache")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache info (sheet_ids, row counts)
        """
        return {
            "cached_sheets": list(self._cache.keys()),
            "sheet_stats": {
                sheet_id: {
                    "rows": len(data['df']),
                    "columns": len(data['columns'])
                }
                for sheet_id, data in self._cache.items()
            }
        }
