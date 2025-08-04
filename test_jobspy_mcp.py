"""
Unit tests for JobSpy MCP Server
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

# Import the server functions
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from server import mcp, scrape_jobs_tool, get_supported_countries, get_supported_sites


class TestJobSpyMCPServer:
    """Test suite for JobSpy MCP Server."""
    
    @pytest.fixture
    def mock_context(self):
        """Create a mock MCP context."""
        ctx = Mock()
        ctx.info = MagicMock()
        ctx.warning = MagicMock()
        ctx.error = MagicMock()
        ctx.report_progress = MagicMock()
        return ctx
    
    @pytest.fixture
    def sample_jobs_df(self):
        """Create sample jobs DataFrame."""
        return pd.DataFrame([
            {
                'title': 'Python Developer',
                'company': 'Tech Corp',
                'location': 'San Francisco, CA',
                'site': 'indeed',
                'job_type': 'fulltime',
                'date_posted': '2024-01-15',
                'min_amount': 80000,
                'max_amount': 120000,
                'currency': 'USD',
                'interval': 'yearly',
                'is_remote': False,
                'job_url': 'https://indeed.com/job/123',
                'description': 'We are looking for a Python developer...'
            },
            {
                'title': 'Remote Data Scientist',
                'company': 'AI Startup',
                'location': 'Remote',
                'site': 'linkedin',
                'job_type': 'fulltime',
                'date_posted': '2024-01-16',
                'min_amount': None,
                'max_amount': None,
                'currency': None,
                'interval': None,
                'is_remote': True,
                'job_url': 'https://linkedin.com/job/456',
                'description': 'Join our AI team as a data scientist...'
            }
        ])
    
    @patch('server.scrape_jobs')
    def test_scrape_jobs_tool_success(self, mock_scrape_jobs, mock_context, sample_jobs_df):
        """Test successful job scraping."""
        # Setup mock
        mock_scrape_jobs.return_value = sample_jobs_df
        
        # Make context methods async
        async def async_mock(*args, **kwargs):
            pass
        
        mock_context.info.side_effect = async_mock
        mock_context.report_progress.side_effect = async_mock
        
        # Test
        result = asyncio.run(
            scrape_jobs_tool(
                search_term="python developer",
                location="San Francisco, CA",
                ctx=mock_context
            )
        )
        
        # Assertions
        assert "Found 2 jobs" in result
        assert "Python Developer" in result
        assert "Tech Corp" in result
        assert "Remote Data Scientist" in result
        assert "AI Startup" in result
        mock_context.info.assert_called()
        mock_context.report_progress.assert_called()
    
    @patch('server.scrape_jobs')
    def test_scrape_jobs_tool_no_results(self, mock_scrape_jobs, mock_context):
        """Test job scraping with no results."""
        # Setup mock
        mock_scrape_jobs.return_value = pd.DataFrame()
        
        # Make context methods async
        async def async_mock(*args, **kwargs):
            pass
        
        mock_context.info.side_effect = async_mock
        mock_context.warning.side_effect = async_mock
        mock_context.report_progress.side_effect = async_mock
        
        # Test
        result = asyncio.run(
            scrape_jobs_tool(
                search_term="nonexistent job",
                ctx=mock_context
            )
        )
        
        # Assertions
        assert "No jobs found" in result
        mock_context.warning.assert_called()
    
    @patch('server.scrape_jobs')
    def test_scrape_jobs_tool_error(self, mock_scrape_jobs, mock_context):
        """Test job scraping with error."""
        # Setup mock to raise exception
        mock_scrape_jobs.side_effect = Exception("Network error")
        
        # Make context methods async
        async def async_mock(*args, **kwargs):
            pass
        
        mock_context.error.side_effect = async_mock
        
        # Test
        result = asyncio.run(
            scrape_jobs_tool(
                search_term="python developer",
                ctx=mock_context
            )
        )
        
        # Assertions
        assert "Error scraping jobs" in result
        assert "Network error" in result
        mock_context.error.assert_called()
    
    def test_scrape_jobs_tool_invalid_sites(self, mock_context):
        """Test job scraping with invalid site names."""
        # Make context methods async
        async def async_mock(*args, **kwargs):
            pass
        
        mock_context.info.side_effect = async_mock
        
        # Test
        result = asyncio.run(
            scrape_jobs_tool(
                search_term="python developer",
                site_name=["invalid_site", "another_invalid"],
                ctx=mock_context
            )
        )
        
        # Assertions
        assert "Invalid site names" in result
        assert "invalid_site" in result
    
    def test_get_supported_countries(self):
        """Test getting supported countries."""
        result = get_supported_countries()
        
        # Assertions
        assert "Supported Countries" in result
        assert "USA" in result
        assert "CANADA" in result
        assert "UK" in result
        assert "Popular Options" in result
    
    def test_get_supported_sites(self):
        """Test getting supported sites."""
        result = get_supported_sites()
        
        # Assertions
        assert "Supported Job Board Sites" in result
        assert "linkedin" in result
        assert "indeed" in result
        assert "glassdoor" in result
        assert "Usage Tips" in result
    
    def test_job_search_tips(self):
        """Test getting job search tips."""
        from server import get_job_search_tips
        
        result = get_job_search_tips()
        
        # Assertions
        assert "JobSpy Job Search Tips" in result
        assert "Search Term Optimization" in result
        assert "Location Strategies" in result
        assert "Performance Tips" in result
        assert "Sample Search Strategies" in result


class TestJobSpyIntegration:
    """Integration tests that require JobSpy."""
    
    @pytest.mark.integration
    def test_real_jobspy_import(self):
        """Test that JobSpy can be imported."""
        try:
            from jobspy import scrape_jobs
            from jobspy.model import Site, Country, JobType
            assert True
        except ImportError:
            pytest.skip("JobSpy not installed")
    
    @pytest.mark.integration 
    @pytest.mark.slow
    def test_real_job_search(self):
        """Test a real job search (slow test)."""
        try:
            from jobspy import scrape_jobs
            
            # Very minimal search
            jobs_df = scrape_jobs(
                site_name=["indeed"],
                search_term="test",
                location="Remote",
                results_wanted=1,
                verbose=0
            )
            
            # Should return DataFrame (even if empty)
            assert isinstance(jobs_df, pd.DataFrame)
            
        except ImportError:
            pytest.skip("JobSpy not installed")
        except Exception as e:
            # Real API calls can fail for various reasons
            pytest.skip(f"Real job search failed (expected): {e}")


def test_server_structure():
    """Test that server has expected structure."""
    from server import mcp
    
    # Check that FastMCP instance exists
    assert mcp is not None
    assert hasattr(mcp, 'run')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
