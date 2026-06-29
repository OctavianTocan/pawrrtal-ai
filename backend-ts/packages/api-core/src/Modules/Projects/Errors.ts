import { Schema } from "effect"
import { Ids } from "../../Lib/TypeIds"

/** Project missing or not owned by the requester (HTTP 404). */
export class ProjectNotFoundError extends Schema.TaggedErrorClass<ProjectNotFoundError>()(
  "ProjectNotFoundError",
  {
    detail: Schema.optional(Schema.String),
    project_id: Schema.optional(Ids.project)
  },
  { httpApiStatus: 404 }
) {}
