import {serveMcp} from '../lib/mcp.mjs';
import {isolatedMcpContext} from '../lib/mcp-context.mjs';
serveMcp('blanket',await isolatedMcpContext('blanket',process.env.B07_MCP_CONTEXT_FILE));
