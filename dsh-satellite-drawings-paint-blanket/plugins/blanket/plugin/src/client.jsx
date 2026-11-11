import {clientPlugin} from '../../../../packages/host-bridge/src/client.jsx';
const plugin=clientPlugin('blanket');
export const inject=plugin.inject; export const apply=plugin.apply;
