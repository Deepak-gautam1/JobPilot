# JobSpy MCP Server

A modern MCP (Model Context Protocol) server that provides job scraping capabilities using the JobSpy library. Built with the latest FastMCP framework for seamless integration with Claude Desktop and other MCP clients.

## 🚀 Features

- **Multi-site job scraping**: Search across 8 major job boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs, Bayt, Naukri, BDJobs)
- **Advanced filtering**: Filter by job type, location, posting date, remote work, salary range, and more
- **Real-time progress**: Get live updates during job searches with progress indicators
- **Rich formatting**: Beautifully formatted job results with all relevant details
- **Modern MCP implementation**: Built with FastMCP for 2025 MCP protocol compliance
- **Error handling**: Robust error handling with informative messages
- **Comprehensive tools**: Multiple tools for job searching, country/site information, and search tips

## 📦 Installation

### Prerequisites
- Python 3.10 or higher
- uv (recommended) or pip

### Quick Install
```bash
# Clone or download the project
cd jobspy-mcp-server

# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .
```

### Install Dependencies Manually
```bash
pip install mcp>=1.1.0 python-jobspy>=1.1.82 pandas>=2.1.0 pydantic>=2.0.0
```

## 🔧 Usage

### Run with uv (Recommended)
```bash
# Development mode with auto-reload
uv run mcp dev server.py

# Production mode
uv run mcp run server.py

# Direct execution
uv run python server.py
```

### Run with Python
```bash
python server.py
```

### Install in Claude Desktop
Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "jobspy": {
      "command": "uv",
      "args": ["run", "python", "/full/path/to/jobspy-mcp-server/server.py"]
    }
  }
}
```

Alternative configuration:
```json
{
  "mcpServers": {
    "jobspy": {
      "command": "python",
      "args": ["/full/path/to/jobspy-mcp-server/server.py"]
    }
  }
}
```

## 🛠️ Available Tools

### 1. `scrape_jobs_tool`
Search for jobs across multiple job boards with comprehensive filtering options.

**Parameters:**
- `search_term` (required): Job keywords (e.g., "software engineer", "data scientist")
- `location`: Job location (e.g., "San Francisco, CA", "Remote")
- `site_name`: List of job boards to search (default: ["indeed", "linkedin", "zip_recruiter", "google"])
- `results_wanted`: Number of results (1-1000, default: 15)
- `job_type`: Employment type ("fulltime", "parttime", "internship", "contract")
- `is_remote`: Filter remote jobs only (default: false)
- `hours_old`: Filter by posting recency in hours
- `distance`: Search radius in miles (1-100, default: 50)
- `easy_apply`: Filter jobs with easy apply (default: false)
- `country_indeed`: Country for Indeed/Glassdoor (default: "usa")
- `linkedin_fetch_description`: Get full LinkedIn descriptions (slower, default: false)
- `offset`: Pagination offset (default: 0)
- `verbose`: Logging level (0-2, default: 1)

### 2. `get_supported_countries`
Get the complete list of supported countries for job searches.

### 3. `get_supported_sites`
Get detailed information about all supported job board sites.

### 4. `get_job_search_tips`
Get comprehensive tips and best practices for effective job searching.

## 💡 Example Queries

Ask Claude:

> "Find me 25 remote Python developer jobs from Indeed and LinkedIn"

> "Search for data scientist positions in San Francisco posted in the last 48 hours"

> "Look for entry-level marketing jobs in New York with easy apply options"

> "Show me all supported job sites and their descriptions"

> "Give me tips for searching software engineering jobs effectively"

## 🌍 Supported Job Boards

- **LinkedIn**: Professional networking platform (rate limited)  
- **Indeed**: Largest job search engine (most reliable)
- **Glassdoor**: Jobs with company reviews and salaries
- **ZipRecruiter**: Job matching for US/Canada
- **Google Jobs**: Aggregated job listings  
- **Bayt**: Middle East job portal
- **Naukri**: India's leading job portal
- **BDJobs**: Bangladesh job portal

## 🌎 Supported Countries

The server supports 50+ countries including:
- USA, Canada, UK, Australia
- Germany, France, Spain, Italy
- India, Singapore, Japan, South Korea
- And many more...

Use `get_supported_countries` tool for the complete list.

## 🚨 Rate Limiting & Best Practices

- **LinkedIn**: Most restrictive, use sparingly
- **Indeed**: Most reliable, good for large searches
- **Start small**: Begin with 10-15 results
- **Use filtering**: Leverage job_type, hours_old, is_remote filters
- **Be specific**: Use targeted search terms for better results

## 🔍 Advanced Search Examples

### Remote Software Jobs
```json
{
  "search_term": "software engineer",
  "location": "Remote", 
  "is_remote": true,
  "site_name": ["indeed", "zip_recruiter"],
  "results_wanted": 20
}
```

### Recent Data Science Jobs
```json
{
  "search_term": "data scientist",
  "location": "San Francisco, CA",
  "hours_old": 48,
  "site_name": ["linkedin", "glassdoor"],
  "linkedin_fetch_description": true
}
```

### Entry Level Positions
```json
{
  "search_term": "junior developer",
  "job_type": "fulltime",
  "easy_apply": true,
  "site_name": ["indeed", "zip_recruiter"],
  "results_wanted": 30
}
```

## 🧪 Testing

Run the test suite:
```bash
# With uv
uv run pytest

# With pip
pip install pytest
pytest
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔧 Troubleshooting

### Common Issues

**"Module not found" errors**
- Ensure all dependencies are installed: `uv sync` or `pip install -e .`

**"No results found"**
- Try broader search terms
- Check different job boards
- Verify location spelling

**Rate limiting/blocking**
- Reduce `results_wanted` parameter
- Use different job boards (avoid LinkedIn for large searches)
- Add delays between searches

**Claude Desktop not detecting tools**
- Verify configuration file path and JSON syntax
- Restart Claude Desktop after configuration changes
- Check server logs for errors

### Getting Help

1. Check the comprehensive `get_job_search_tips` tool
2. Review the example queries above
3. Start with small searches and expand gradually
4. Use verbose logging (`verbose=2`) for debugging

## 🚀 Quick Start

1. Install: `uv sync`
2. Test: `uv run mcp dev server.py`  
3. Configure Claude Desktop with the server path
4. Ask Claude: "Find me remote Python jobs using JobSpy"

Happy job hunting! 🎯
