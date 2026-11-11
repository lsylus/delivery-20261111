import {serveMcp} from '../lib/mcp.mjs';
import {isolatedMcpContext} from '../lib/mcp-context.mjs';
serveMcp('paint',await isolatedMcpContext('paint',process.env.B07_MCP_CONTEXT_FILE));
