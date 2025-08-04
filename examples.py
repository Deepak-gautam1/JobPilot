#!/usr/bin/env python3
"""
Example usage script for JobSpy MCP Server
Shows how to use the server programmatically
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def demo_job_search():
    """Demonstrate job searching capabilities."""
    
    # Server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                print("🔗 Connected to JobSpy MCP Server")
                
                # Initialize
                await session.initialize()
                
                # List available tools
                tools = await session.list_tools()
                print(f"📋 Available tools: {[t.name for t in tools.tools]}")
                
                # Get supported sites
                print("\n🔍 Getting supported job sites...")
                sites_result = await session.call_tool(
                    "get_supported_sites",
                    arguments={}
                )
                print(sites_result.content[0].text[:500] + "...")
                
                # Search for jobs
                print("\n🎯 Searching for Python developer jobs...")
                search_result = await session.call_tool(
                    "scrape_jobs_tool",
                    arguments={
                        "search_term": "python developer",
                        "location": "Remote",
                        "site_name": ["indeed"],
                        "results_wanted": 5,
                        "is_remote": True,
                        "verbose": 1
                    }
                )
                
                print(f"✅ Job search completed!")
                print(f"📊 Results preview:")
                result_text = search_result.content[0].text
                print(result_text[:800] + "..." if len(result_text) > 800 else result_text)
                
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_static_usage():
    """Show static examples without running server."""
    print("💡 Example Usage Patterns:")
    print("=" * 50)
    
    examples = [
        {
            "name": "Remote Software Jobs",
            "params": {
                "search_term": "software engineer",
                "location": "Remote",
                "is_remote": True,
                "site_name": ["indeed", "zip_recruiter"],
                "results_wanted": 20
            }
        },
        {
            "name": "Recent Data Science Jobs",
            "params": {
                "search_term": "data scientist",
                "location": "San Francisco, CA",
                "hours_old": 48,
                "site_name": ["linkedin", "glassdoor"],
                "linkedin_fetch_description": True
            }
        },
        {
            "name": "Entry Level Marketing",
            "params": {
                "search_term": "marketing coordinator",
                "job_type": "fulltime",
                "easy_apply": True,
                "site_name": ["indeed", "zip_recruiter"],
                "results_wanted": 15
            }
        },
        {
            "name": "Contract Developer Jobs",
            "params": {
                "search_term": "react developer",
                "job_type": "contract",
                "location": "Austin, TX",
                "distance": 25,
                "site_name": ["indeed", "glassdoor"]
            }
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}")
        print(f"   Parameters: {json.dumps(example['params'], indent=6)}")
    
    print("\n🤖 Claude Desktop Examples:")
    claude_examples = [
        "Find me 25 remote Python jobs from Indeed and LinkedIn",
        "Search for data scientist roles in NYC posted in the last week",
        "Show me entry-level marketing jobs with easy apply",
        "What countries are supported for job searches?",
        "Give me tips for effective job searching"
    ]
    
    for example in claude_examples:
        print(f"   • \"{example}\"")


async def main():
    """Main demo function."""
    print("🚀 JobSpy MCP Server Examples")
    print("=" * 40)
    
    print("Choose demo mode:")
    print("1. Interactive demo (requires running server)")
    print("2. Static examples (no server needed)")
    
    try:
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            await demo_job_search()
        else:
            demo_static_usage()
            
    except KeyboardInterrupt:
        print("\n👋 Demo cancelled")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("\n💡 Try running: python test_server.py first")


if __name__ == "__main__":
    asyncio.run(main())
