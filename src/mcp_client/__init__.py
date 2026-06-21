"""MCP client wrapper package.

Thin, testable boundary over an MCP session: connect, discover tools
(mapped to Ollama's tool-calling schema), and call tools. See client.py
for the implementation; PRD §8 for the architecture this fits into.
"""
