import { Schema } from "effect"
import { HttpApiEndpoint, HttpApiGroup, HttpApiSchema, OpenApi } from "effect/unstable/httpapi"
import { Ids } from "../../Lib/TypeIds"
import { AllowedUserMiddlewareService, AuthenticationMiddlewareService } from "../Auth/Api"
import { Project, ProjectCreateInput, ProjectUpdateInput } from "./Domain"
import { ProjectNotFoundError } from "./Errors"

/** Authenticated CRUD for `/api/v1/projects`. */
export class ProjectsApi extends HttpApiGroup.make("projects")
  .add(
    HttpApiEndpoint.get("list", "/", {
      success: Schema.Array(Project)
    })
      .annotate(OpenApi.Summary, "List projects")
      .annotate(OpenApi.Description, "List every project for the authenticated user")
  )
  .add(
    HttpApiEndpoint.post("create", "/", {
      payload: ProjectCreateInput,
      success: Project.pipe(HttpApiSchema.status("Created"))
    })
      .annotate(OpenApi.Summary, "Create project")
      .annotate(OpenApi.Description, "Create a new project for the authenticated user")
  )
  .add(
    HttpApiEndpoint.patch("update", "/:project_id", {
      params: {
        project_id: Ids.project
      },
      payload: ProjectUpdateInput,
      success: Project,
      error: ProjectNotFoundError
    })
      .annotate(OpenApi.Summary, "Update project")
      .annotate(OpenApi.Description, "Rename a project (only `name` is mutable today)")
  )
  .add(
    HttpApiEndpoint.delete("delete", "/:project_id", {
      params: {
        project_id: Ids.project
      },
      success: HttpApiSchema.NoContent,
      error: ProjectNotFoundError
    })
      .annotate(OpenApi.Summary, "Delete project")
      .annotate(OpenApi.Description, "Delete a project; linked conversations are unlinked, not deleted")
  )
  .middleware(AllowedUserMiddlewareService)
  .middleware(AuthenticationMiddlewareService)
  .prefix("/projects") {}
