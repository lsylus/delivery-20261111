import {clientPlugin} from '../../../../packages/host-bridge/src/client.jsx';
const plugin=clientPlugin('paint');
export const inject=plugin.inject; export const apply=plugin.apply;
