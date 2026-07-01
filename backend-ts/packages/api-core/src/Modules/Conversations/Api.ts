import { Schema } from "effect"
import { HttpApiEndpoint, HttpApiGroup, HttpApiSchema, OpenApi } from "effect/unstable/httpapi"
import { Ids } from "../../Lib/TypeIds"
import { AllowedUserMiddlewareService, AuthenticationMiddlewareService } from "../Auth/Api"
import { ChatMessageRead, Conversation, ConversationCreateInput, ConversationUpdateInput } from "./Domain"
import { ConversationAlreadyExistsError, ConversationNotFoundError } from "./Errors"

/** Authenticated CRUD for `/api/v1/conversations`. */
export class ConversationsApi extends HttpApiGroup.make("conversations")
  .add(
    HttpApiEndpoint.get("list", "/", {
      success: Schema.Array(Conversation)
    })
      .annotate(OpenApi.Summary, "List conversations")
      .annotate(OpenApi.Description, "List every conversation for the authenticated user")
  )
  .add(
    HttpApiEndpoint.post("create", "/:conversation_id", {
      params: {
        conversation_id: Ids.conversation
      },
      payload: ConversationCreateInput,
      success: Conversation.pipe(HttpApiSchema.status("Created")),
      error: ConversationAlreadyExistsError
    })
      .annotate(OpenApi.Summary, "Create conversation")
      .annotate(OpenApi.Description, "Create a new conversation for the authenticated user")
  )
  .add(
    HttpApiEndpoint.get("get", "/:conversation_id", {
      params: {
        conversation_id: Ids.conversation
      },
      success: Conversation,
      error: ConversationNotFoundError
    })
      .annotate(OpenApi.Summary, "Get conversation")
      .annotate(OpenApi.Description, "Get a conversation by ID")
  )
  .add(
    HttpApiEndpoint.patch("update", "/:conversation_id", {
      params: {
        conversation_id: Ids.conversation
      },
      payload: ConversationUpdateInput,
      success: Conversation,
      error: ConversationNotFoundError
    })
      .annotate(OpenApi.Summary, "Update conversation")
      .annotate(OpenApi.Description, "Update a conversation by ID")
  )
  .add(
    HttpApiEndpoint.delete("delete", "/:conversation_id", {
      params: {
        conversation_id: Ids.conversation
      },
      success: HttpApiSchema.NoContent,
      error: ConversationNotFoundError
    })
      .annotate(OpenApi.Summary, "Delete conversation")
      .annotate(OpenApi.Description, "Delete a conversation by ID")
  )
  .add(
    HttpApiEndpoint.get("messages", "/:conversation_id/messages", {
      params: {
        conversation_id: Ids.conversation
      },
      success: Schema.Array(ChatMessageRead),
      error: ConversationNotFoundError
    })
      .annotate(OpenApi.Summary, "Get messages")
      .annotate(OpenApi.Description, "Get messages by conversation ID")
  )
  .middleware(AllowedUserMiddlewareService)
  .middleware(AuthenticationMiddlewareService)
  .prefix("/conversations") {}
