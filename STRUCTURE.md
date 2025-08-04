# JobSpy MCP Server - File Structure

## 📁 Project Structure

```
jobspy-mcp-server/
├── server.py                 # Main MCP server implementation (FastMCP)
├── pyproject.toml            # Project configuration and dependencies
├── README.md                 # Comprehensive documentation
├── LICENSE                   # MIT license
├── setup.py                  # Quick installation script
├── test_server.py            # Server testing and validation
├── test_jobspy_mcp.py        # Unit tests
├── examples.py               # Usage examples and demos
├── uv.lock                   # uv dependency lock file
└── STRUCTURE.md              # This file
```

## 🔧 Key Files

### `server.py` - Main Server
- **Modern FastMCP implementation** (2025 MCP protocol)
- **4 tools available**:
  - `scrape_jobs_tool`: Main job searching with full parameter support
  - `get_supported_countries`: List supported countries
  - `get_supported_sites`: List job board sites with descriptions
  - `get_job_search_tips`: Comprehensive search guidance
- **Progress reporting** with real-time updates
- **Rich formatting** of job results
- **Error handling** with informative messages

### `pyproject.toml` - Configuration
- **Modern Python packaging** with hatchling
- **Dependencies**: mcp>=1.1.0, python-jobspy>=1.1.82, pandas, pydantic
- **Development tools**: pytest, black, mypy
- **Entry points** for command-line usage

### `README.md` - Documentation
- **Complete setup instructions** for multiple environments
- **Usage examples** with Claude Desktop integration
- **Tool documentation** with parameter descriptions
- **Troubleshooting guide** with common issues
- **Best practices** for effective job searching

### `test_server.py` - Testing
- **Dependency verification** 
- **Server startup testing**
- **MCP dev mode testing**
- **Configuration generation**
- **Usage examples**

### `setup.py` - Quick Setup
- **Automated dependency installation**
- **uv and pip support**
- **Claude Desktop config generation**
- **Next steps guidance**

## 🚀 Quick Start

1. **Install**: `python setup.py` or `uv sync`
2. **Test**: `python test_server.py`
3. **Run**: `uv run mcp dev server.py`
4. **Configure**: Add to Claude Desktop config
5. **Use**: Ask Claude to find jobs!

## 🛠️ Development

### Running Tests
```bash
# Unit tests
python -m pytest test_jobspy_mcp.py -v

# Server tests  
python test_server.py

# Integration tests (slow)
python -m pytest test_jobspy_mcp.py -m integration
```

### Development Mode
```bash
# MCP inspector (recommended)
uv run mcp dev server.py

# Direct execution
python server.py

# With auto-reload
uv run mcp dev server.py --reload
```

### Code Quality
```bash
# Format code
black server.py test_*.py

# Type checking
mypy server.py

# Run all tests
pytest
```

## 📦 Dependencies

### Core Dependencies
- **mcp>=1.1.0**: Latest Model Context Protocol framework
- **python-jobspy>=1.1.82**: Job scraping library with 8 job boards
- **pandas>=2.1.0**: Data manipulation and analysis
- **pydantic>=2.0.0**: Data validation and serialization

### Development Dependencies
- **pytest>=7.0.0**: Testing framework
- **black>=23.0.0**: Code formatter
- **mypy>=1.0.0**: Static type checker
- **pre-commit>=3.0.0**: Git hooks for code quality

## 🔌 MCP Protocol Features

### FastMCP Implementation
- **Modern decorators**: `@mcp.tool()` for clean tool definitions
- **Type safety**: Full type hints and validation
- **Progress reporting**: Real-time progress updates with `ctx.report_progress()`
- **Logging**: Structured logging with `ctx.info()`, `ctx.warning()`, `ctx.error()`
- **Error handling**: Proper exception handling and user feedback

### Tool Capabilities
- **Rich parameters**: Complex parameter validation with JSON schemas
- **Formatted output**: Markdown-formatted responses for readability
- **Progress tracking**: Live updates during long-running job searches
- **Error recovery**: Graceful handling of rate limits and API failures

## 🌐 Supported Job Boards

### Primary Sites (Most Reliable)
- **Indeed**: Global job search engine, best rate limits
- **ZipRecruiter**: US/Canada focused, good for volume searches
- **Google Jobs**: Aggregated listings, requires specific search terms

### Professional Networks
- **LinkedIn**: High-quality jobs, strict rate limiting
- **Glassdoor**: Jobs with company insights and salaries

### Regional Specialists
- **Bayt**: Middle East and North Africa
- **Naukri**: India's leading job portal
- **BDJobs**: Bangladesh job market

## 🌍 Geographic Coverage

### Fully Supported Countries (50+)
- **North America**: USA, Canada
- **Europe**: UK, Germany, France, Spain, Italy, Netherlands, etc.
- **Asia-Pacific**: Australia, India, Singapore, Japan, etc.
- **Middle East**: UAE, Saudi Arabia, Qatar, etc.
- **Others**: Brazil, Mexico, South Africa, etc.

### Usage Patterns
- **Indeed/Glassdoor**: Use country-specific domains
- **LinkedIn**: Global search with location filtering
- **Regional sites**: Automatic country targeting

## 🔧 Configuration Options

### Claude Desktop Integration
```json
{
  "mcpServers": {
    "jobspy": {
      "command": "uv",
      "args": ["run", "python", "/path/to/server.py"]
    }
  }
}
```

### Alternative Configurations
- **Direct Python**: Use `python` command instead of `uv`
- **Virtual Environment**: Activate venv before running
- **Docker**: Containerized deployment (advanced)

## 🎯 Usage Patterns

### Beginner Searches
```python
# Simple remote job search
search_term="software engineer"
location="Remote"
is_remote=True
site_name=["indeed", "zip_recruiter"]
```

### Advanced Searches
```python
# Comprehensive search with filters
search_term="data scientist"
location="San Francisco, CA"
hours_old=48
job_type="fulltime"
linkedin_fetch_description=True
site_name=["linkedin", "glassdoor", "indeed"]
```

### Bulk Searches
```python
# Large result sets with pagination
results_wanted=100
offset=0  # Start from beginning
site_name=["indeed"]  # Most reliable for bulk
```

## 🚨 Rate Limiting & Best Practices

### Site-Specific Limits
- **LinkedIn**: ~10-20 requests/hour, strict blocking
- **Indeed**: Most lenient, supports large searches
- **Glassdoor**: Moderate limits, good for medium searches
- **Others**: Varies by region and usage patterns

### Optimization Strategies
- **Start small**: Begin with 10-15 results
- **Single site testing**: Test with Indeed first
- **Progressive expansion**: Add more sites gradually
- **Use filtering**: Leverage job_type, hours_old, is_remote
- **Batch processing**: Use offset for pagination

## 🐛 Troubleshooting

### Common Issues
1. **"No results found"**
   - Try broader search terms
   - Check different job boards
   - Verify location spelling

2. **Rate limiting/blocking**
   - Reduce results_wanted
   - Avoid LinkedIn for large searches
   - Add delays between requests

3. **"Module not found"**
   - Run `uv sync` or `pip install -e .`
   - Check Python path configuration

4. **Claude Desktop not detecting**
   - Verify JSON syntax in config
   - Check file paths are absolute
   - Restart Claude Desktop

### Debug Mode
```bash
# Enable verbose logging
python server.py --verbose=2

# Test with MCP inspector
uv run mcp dev server.py

# Run test suite
python test_server.py
```

## 🔄 Development Workflow

### Setup Development Environment
```bash
git clone <your-repo>
cd jobspy-mcp-server
uv sync
uv run pre-commit install
```

### Testing Changes
```bash
# Run unit tests
pytest test_jobspy_mcp.py -v

# Test server functionality
python test_server.py

# Test with MCP inspector
uv run mcp dev server.py
```

### Code Quality
```bash
# Format code
black .

# Type checking
mypy server.py

# Run all checks
pre-commit run --all-files
```

## 📈 Performance Considerations

### Memory Usage
- **Small searches (1-20 jobs)**: ~50MB RAM
- **Medium searches (50-100 jobs)**: ~100-200MB RAM
- **Large searches (500+ jobs)**: ~500MB+ RAM

### Processing Time
- **Indeed (20 jobs)**: 5-15 seconds
- **LinkedIn (20 jobs)**: 10-30 seconds
- **Multi-site (20 jobs each)**: 30-60 seconds
- **Description fetching**: +2-5 seconds per job

### Optimization Tips
- **Disable description fetching** for faster searches
- **Use specific sites** instead of all sites
- **Implement caching** for repeated searches
- **Process results in batches** for large datasets

## 🚀 Future Enhancements

### Planned Features
- **Caching layer**: Store recent searches
- **Async processing**: Parallel job board queries
- **Filter persistence**: Save common search filters
- **Export formats**: CSV, JSON, PDF exports
- **Notification system**: Alert for new matching jobs

### Integration Possibilities
- **Calendar integration**: Schedule job searches
- **Email notifications**: Send job alerts
- **CRM integration**: Export to job tracking systems
- **Analytics dashboard**: Track search patterns

---

## 📞 Support

### Getting Help
1. **Read documentation**: Start with README.md
2. **Run diagnostics**: Use test_server.py
3. **Check examples**: Review examples.py
4. **Enable verbose logging**: Set verbose=2
5. **Test incrementally**: Start with simple searches

### Contributing
1. **Fork repository**
2. **Create feature branch**
3. **Add tests** for new functionality
4. **Run quality checks**
5. **Submit pull request**

---

**Built with ❤️ using FastMCP and JobSpy**
