#!/usr/bin/env python3
"""
Simple installation script for JobSpy MCP Server
Designed for virtual environments and direct pip usage
"""

import subprocess
import sys
import json
from pathlib import Path


def install_with_pip():
    """Install dependencies using pip."""
    print("📦 Installing dependencies with pip...")
    
    dependencies = [
        "mcp>=1.1.0",
        "python-jobspy>=1.1.82", 
        "pandas>=2.1.0",
        "pydantic>=2.0.0"
    ]
    
    for dep in dependencies:
        print(f"🔄 Installing {dep}...")
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "install", dep], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {dep} installed")
            else:
                print(f"❌ Failed to install {dep}: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error installing {dep}: {e}")
            return False
    
    return True


def test_imports():
    """Test that all required packages can be imported."""
    print("\n🧪 Testing imports...")
    
    tests = [
        ("mcp", "MCP framework"),
        ("jobspy", "JobSpy library"),
        ("pandas", "Pandas"),
        ("pydantic", "Pydantic")
    ]
    
    for module, name in tests:
        try:
            __import__(module)
            print(f"✅ {name} imported successfully")
        except ImportError as e:
            print(f"❌ {name} import failed: {e}")
            return False
    
    return True


def create_claude_config():
    """Create Claude Desktop configuration."""
    print("\n📄 Creating Claude Desktop configuration...")
    
    current_dir = Path.cwd().absolute()
    server_path = current_dir / "server.py"
    
    # Simple configuration for your environment
    config = {
        "mcpServers": {
            "jobspy": {
                "command": "python3",
                "args": [str(server_path)],
                "env": {
                    "PYTHONPATH": str(current_dir)
                }
            }
        }
    }
    
    # Save configuration
    with open("claude_config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print("✅ Configuration saved to: claude_config.json")
    
    return config


def show_config_instructions(config):
    """Show how to configure Claude Desktop."""
    print("\n" + "=" * 60)
    print("🎉 Setup Complete!")
    print("=" * 60)
    
    print("\n📋 Claude Desktop Setup:")
    print("1. Open Claude Desktop configuration file:")
    
    if sys.platform == "darwin":
        config_path = "~/Library/Application Support/Claude/claude_desktop_config.json"
        print(f"   {config_path}")
    elif sys.platform == "win32":
        config_path = "%APPDATA%/Claude/claude_desktop_config.json"
        print(f"   {config_path}")
    else:
        print("   (Location varies by OS)")
    
    print("\n2. Add this configuration:")
    print(json.dumps(config, indent=2))
    
    print("\n3. Restart Claude Desktop")
    
    print("\n🧪 Testing:")
    print("   python test_server.py")
    print("   python server.py")
    
    print("\n💡 Usage with Claude:")
    print('   "Find me remote Python jobs"')
    print('   "Show supported job sites"')
    print('   "Search for data scientist jobs in SF"')


def main():
    """Main setup function."""
    print("🚀 JobSpy MCP Server Setup (Virtual Environment)")
    print("=" * 55)
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("❌ Python 3.10+ required")
        return False
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Install dependencies
    if not install_with_pip():
        print("\n❌ Installation failed")
        return False
    
    # Test imports
    if not test_imports():
        print("\n❌ Import tests failed")
        return False
    
    # Create configuration
    config = create_claude_config()
    
    # Show instructions
    show_config_instructions(config)
    
    return True


if __name__ == "__main__":
    success = main()
    if not success:
        print("\n💡 Manual installation:")
        print("pip install mcp python-jobspy pandas pydantic")
    sys.exit(0 if success else 1)
