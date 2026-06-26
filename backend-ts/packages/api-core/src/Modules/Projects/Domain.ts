/** Domain schemas for projects. */

import { Schema } from "effect"
import { Ids } from "../../Lib/TypeIds"

export const ProjectId = Ids.project
export type ProjectId = Schema.Schema.Type<typeof ProjectId>

export const UserId = Ids.user
export type UserId = Schema.Schema.Type<typeof UserId>

export class Project extends Schema.Class<Project>("Project")(
  {
    id: ProjectId,
    user_id: UserId,
    name: Schema.String.annotate({
      description: "Display name shown in the sidebar"
    }),
    created_at: Schema.DateTimeUtcFromString.annotate({
      description: "Creation timestamp"
    }),
    updated_at: Schema.DateTimeUtcFromString.annotate({
      description: "Last update timestamp"
    })
  },
  {
    identifier: "Project",
    title: "Project",
    description: "A project is a collection of conversations"
  }
) {}

export class ProjectCreateInput extends Schema.Class<ProjectCreateInput>("ProjectCreateInput")(
  {
    name: Schema.String.annotate({
      description: "Project name (empty/whitespace may become Untitled Project in service)"
    })
  },
  {
    identifier: "ProjectCreateInput",
    title: "ProjectCreateInput",
    description: "Payload for creating a new project"
  }
) {}

export class ProjectUpdateInput extends Schema.Class<ProjectUpdateInput>("ProjectUpdateInput")(
  {
    name: Schema.NullOr(Schema.String).annotate({
      description: "New project name; omit to keep current name"
    })
  },
  {
    identifier: "ProjectUpdateInput",
    title: "ProjectUpdateInput",
    description: "Payload for updating an existing project"
  }
) {}
