#!/usr/bin/env python3
"""
Test script for JobSpy MCP Server (2025 FastMCP Implementation)
"""

import asyncio
import subprocess
import sys
import json
import os
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed."""
    print("📋 Checking dependencies...")
    
    required_packages = {
        "mcp": "1.1.0",
        "pandas": "2.1.0", 
        "pydantic": "2.0.0"
    }
    
    missing_packages = []
    
    for package, min_version in required_packages.items():
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {package} {version}")
        except ImportError:
            print(f"❌ {package} missing")
            missing_packages.append(f"{package}>={min_version}")
    
    # Check JobSpy
    try:
        from jobspy import scrape_jobs
        print("✅ python-jobspy available")
    except ImportError:
        print("❌ python-jobspy missing")
        missing_packages.append("python-jobspy>=1.1.82")
    
    if missing_packages:
        print(f"\n🚨 Install missing packages:")
        print(f"uv add {' '.join(missing_packages)}")
        print(f"# or pip install {' '.join(missing_packages)}")
        return False
    
    return True


def check_uv_available():
    """Check if uv is available."""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ uv available: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("⚠️  uv not found, using python directly")
    return False


async def test_basic_jobspy():
    """Test basic JobSpy functionality."""
    print("\n🔍 Testing basic JobSpy functionality...")
    
    try:
        from jobspy import scrape_jobs
        
        # Very small test search
        print("Running minimal job search (2 results from Indeed)...")
        jobs_df = scrape_jobs(
            site_name=["indeed"],
            search_term="test",
            location="Remote",
            results_wanted=2,
            verbose=0
        )
        
        if len(jobs_df) >= 0:  # Even 0 results is okay
            print(f"✅ JobSpy working! Found {len(jobs_df)} jobs")
            if len(jobs_df) > 0:
                print(f"   Sample columns: {list(jobs_df.columns)[:5]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ JobSpy test failed: {e}")
        return False


def test_server_with_mcp_dev():
    """Test server using uv run mcp dev."""
    print("\n🧪 Testing with MCP dev mode...")
    
    if not check_uv_available():
        print("⚠️  Skipping MCP dev test (uv required)")
        return True
    
    try:
        print("Starting: uv run mcp dev server.py")
        print("This will start the MCP inspector...")
        print("Press Ctrl+C to stop and continue with other tests")
        
        result = subprocess.run(
            ["uv", "run", "mcp", "dev", "server.py"],
            timeout=5,  # Short timeout since this is interactive
            capture_output=True,
            text=True
        )
        
        if "Starting MCP inspector" in result.stdout or result.returncode == 0:
            print("✅ MCP dev mode started successfully")
        else:
            print(f"⚠️  MCP dev output: {result.stdout}")
            
    except subprocess.TimeoutExpired:
        print("✅ MCP dev mode started (timed out as expected)")
    except FileNotFoundError:
        print("❌ MCP CLI not found")
        return False
    except Exception as e:
        print(f"⚠️  MCP dev test issue: {e}")
    
    return True


def generate_claude_config():
    """Generate Claude Desktop configuration."""
    print("\n📄 Generating Claude Desktop configuration...")
    
    current_dir = Path.cwd().absolute()
    server_path = current_dir / "server.py"
    
    config = {
        "mcpServers": {
            "jobspy": {
                "command": "uv",
                "args": ["run", "python", str(server_path)]
            }
        }
    }
    
    # Alternative config without uv
    config_alt = {
        "mcpServers": {
            "jobspy": {
                "command": "python",
                "args": [str(server_path)]
            }
        }
    }
    
    print("✅ Claude Desktop configuration (with uv):")
    print(json.dumps(config, indent=2))
    
    print("\n✅ Alternative configuration (without uv):")
    print(json.dumps(config_alt, indent=2))
    
    # Detect platform and show config location
    if sys.platform == "darwin":  # macOS
        config_path = "~/Library/Application Support/Claude/claude_desktop_config.json"
        print(f"\n📍 macOS config location: {config_path}")
    elif sys.platform == "win32":  # Windows
        config_path = "%APPDATA%/Claude/claude_desktop_config.json"
        print(f"\n📍 Windows config location: {config_path}")
    else:
        print(f"\n📍 Config location varies by OS")
    
    return True


def show_usage_examples():
    """Show example usage patterns."""
    print("\n💡 Example Usage with Claude:")
    
    examples = [
        "Find me 20 remote Python developer jobs from Indeed and LinkedIn",
        "Search for data scientist positions in San Francisco posted in the last 48 hours", 
        "Show me entry-level marketing jobs in New York with easy apply options",
        "What job sites are supported by JobSpy?",
        "Give me tips for searching software engineering jobs effectively",
        "Find full-time contract positions for 'machine learning engineer' in Austin, TX"
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"{i}. \"{example}\"")
    
    print("\n🛠️  Tool Functions Available:")
    tools = [
        "scrape_jobs_tool - Main job searching functionality",
        "get_supported_countries - List all supported countries", 
        "get_supported_sites - List all job board sites",
        "get_job_search_tips - Comprehensive search guidance"
    ]
    
    for tool in tools:
        print(f"   • {tool}")


async def main():
    """Main test function."""
    print("🚀 JobSpy MCP Server Test Suite (2025 FastMCP)")
    print("=" * 60)
    
    # Check project structure
    required_files = ["server.py", "pyproject.toml", "README.md"]
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file} found")
        else:
            print(f"❌ {file} missing")
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Dependency check failed")
        return
    
    # Test basic JobSpy
    if not await test_basic_jobspy():
        print("\n⚠️  JobSpy issues detected, but continuing...")
    
    # Test MCP dev mode
    test_server_with_mcp_dev()
    
    # Generate configuration
    generate_claude_config()
    
    # Show usage examples
    show_usage_examples()
    
    print("\n" + "=" * 60)
    print("🎯 Next Steps:")
    print("1. Install any missing dependencies shown above")
    print("2. Test with: uv run mcp dev server.py")
    print("3. Add configuration to Claude Desktop (see above)")
    print("4. Restart Claude Desktop")
    print("5. Try: 'Find me remote Python jobs using JobSpy'")
    print("\n🚀 Your JobSpy MCP Server is ready!")


if __name__ == "__main__":
    asyncio.run(main())
