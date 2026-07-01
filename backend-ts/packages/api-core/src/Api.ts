import { HttpApi, OpenApi } from 'effect/unstable/httpapi';
import { ConversationsApi } from './Modules/Conversations/Api';
import { ProjectsApi } from './Modules/Projects/Api';
import { SystemApi } from './Modules/System/Api';

/** Root HttpApi at `/api/v1`; handlers live in `apps/api`. */
export class Api extends HttpApi.make('api')
  .add(SystemApi)
  .add(ProjectsApi)
  .add(ConversationsApi)
  .prefix('/api/v1')
  .annotate(OpenApi.Title, 'Pawrrtal API')
  .annotate(OpenApi.Version, '1.0.0')
  .annotate(OpenApi.Description, 'Pawrrtal API') {}
