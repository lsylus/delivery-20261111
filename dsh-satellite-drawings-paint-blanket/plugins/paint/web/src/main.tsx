import React from 'react';
import {createRoot} from 'react-dom/client';
import {Workbench} from '../../../../packages/workbench-common/src/Workbench';
import '../../../../packages/workbench-common/src/style.css';
createRoot(document.getElementById('root')!).render(<Workbench module='paint'/>);
