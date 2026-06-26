import { Schema } from "effect"
import { ProjectId } from "./Domain"

/** Project missing or not owned by the requester (HTTP 404). */
export class ProjectNotFoundError extends Schema.TaggedErrorClass<ProjectNotFoundError>()(
  "ProjectNotFoundError",
  {
    detail: Schema.optional(Schema.String),
    project_id: Schema.optional(ProjectId)
  },
  { httpApiStatus: 404 }
) {}
