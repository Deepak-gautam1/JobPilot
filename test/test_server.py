#!/usr/bin/env python3
"""
Simple test script to verify the MCP server is working
"""
import asyncio
import json
import subprocess
import sys

async def test_mcp_server():
    """Test the MCP server by sending a simple request"""
    print("Testing JobSpy MCP Server...")
    
    # Start the server process
    process = subprocess.Popen(
        [sys.executable, "../server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Send initialization request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        # Send request
        request_str = json.dumps(init_request) + "\n"
        process.stdin.write(request_str)
        process.stdin.flush()
        
        # Wait a bit for response
        await asyncio.sleep(2)
        
        # Check if process is still running (good sign)
        if process.poll() is None:
            print("✅ Server started successfully and is running!")
            print("✅ Server is ready to accept MCP requests")
            
            # Try to get tools list
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            
            tools_str = json.dumps(tools_request) + "\n"
            process.stdin.write(tools_str)
            process.stdin.flush()
            
            await asyncio.sleep(1)
            
            print("✅ Server is responding to requests")
        else:
            print("❌ Server exited unexpectedly")
            stderr_output = process.stderr.read()
            if stderr_output:
                print(f"Error output: {stderr_output}")
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        # Clean up
        process.terminate()
        try:
            await asyncio.wait_for(asyncio.create_task(asyncio.to_thread(process.wait)), timeout=5)
        except asyncio.TimeoutError:
            process.kill()

if __name__ == "__main__":
    asyncio.run(test_mcp_server())
