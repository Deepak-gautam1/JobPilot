# -------- JobSpy MCP Server Docker image ----------
# Build:   docker build -t jobspy-mcp-server .
# Run:     docker run --rm -it jobspy-mcp-server
# The container starts the server on stdio; connect via MCP client.

FROM python:3.11-slim

# Install uv (fast lockfile installer) and other build deps
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project and lockfile first (better cache)
COPY requirements.lock ./
RUN uv pip sync requirements.lock

# Copy the rest of the source
COPY . .

# Install editable package (no network; deps already satisfied)
RUN pip install -e .

CMD ["jobspy-mcp-server"]
