import React from 'react';
import {createRoot} from 'react-dom/client';
import {BlanketWorkbench} from './BlanketWorkbench';
import '../../../../packages/workbench-common/src/style.css';
createRoot(document.getElementById('root')!).render(<BlanketWorkbench/>);
