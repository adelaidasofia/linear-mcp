"""GraphQL query and mutation strings + reusable fragments.

Kept in one module so tools compose against a stable shape and field
churn happens in one place. Field selections lean toward what a downstream
agent will want (titles, urls, identifiers) without dumping massive
nested payloads.
"""

from __future__ import annotations

# --- Reusable fragments -----------------------------------------------------

USER_FIELDS = """
  id name displayName email avatarUrl active admin url
  isMe createdAt updatedAt
"""

TEAM_FIELDS = """
  id key name description icon color private timezone
  createdAt updatedAt
"""

WORKFLOW_STATE_FIELDS = """
  id name type color position description
  team { id key name }
"""

LABEL_FIELDS = """
  id name color description
  team { id key name }
  parent { id name }
"""

ISSUE_FIELDS = """
  id identifier title description priority priorityLabel
  url branchName estimate
  state { id name type color }
  assignee { id name displayName email }
  creator { id name displayName }
  team { id key name }
  project { id name }
  projectMilestone { id name }
  cycle { id number name }
  parent { id identifier title }
  labels { nodes { id name color } }
  createdAt updatedAt completedAt canceledAt startedAt
  dueDate snoozedUntilAt archivedAt
"""

PROJECT_FIELDS = """
  id name description content slugId url icon color
  state status { id name type color }
  priority priorityLabel progress
  startDate targetDate completedAt canceledAt archivedAt
  lead { id name displayName }
  teams { nodes { id key name } }
  initiatives { nodes { id name } }
  createdAt updatedAt
"""

INITIATIVE_FIELDS = """
  id name description content slugId url icon color
  status targetDate
  owner { id name displayName }
  projects { nodes { id name } }
  createdAt updatedAt archivedAt
"""

MILESTONE_FIELDS = """
  id name description targetDate sortOrder
  project { id name }
  createdAt updatedAt archivedAt
"""

CYCLE_FIELDS = """
  id number name description startsAt endsAt completedAt
  progress
  team { id key name }
  createdAt updatedAt
"""

COMMENT_FIELDS = """
  id body url
  user { id name displayName }
  issue { id identifier title }
  parent { id }
  createdAt updatedAt editedAt
"""

DOCUMENT_FIELDS = """
  id title content slugId url icon color
  creator { id name displayName }
  updatedBy { id name displayName }
  project { id name }
  initiative { id name }
  createdAt updatedAt archivedAt
"""

PAGE_INFO = "pageInfo { hasNextPage endCursor }"


# --- List queries -----------------------------------------------------------

LIST_TEAMS = f"""
query ListTeams($first: Int, $after: String) {{
  teams(first: $first, after: $after) {{
    nodes {{ {TEAM_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_USERS = f"""
query ListUsers($first: Int, $after: String, $includeDisabled: Boolean) {{
  users(first: $first, after: $after, includeDisabled: $includeDisabled) {{
    nodes {{ {USER_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_PROJECTS = f"""
query ListProjects($first: Int, $after: String, $filter: ProjectFilter) {{
  projects(first: $first, after: $after, filter: $filter) {{
    nodes {{ {PROJECT_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_INITIATIVES = f"""
query ListInitiatives($first: Int, $after: String) {{
  initiatives(first: $first, after: $after) {{
    nodes {{ {INITIATIVE_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_ISSUES = f"""
query ListIssues($first: Int, $after: String, $filter: IssueFilter, $orderBy: PaginationOrderBy) {{
  issues(first: $first, after: $after, filter: $filter, orderBy: $orderBy) {{
    nodes {{ {ISSUE_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_CYCLES = f"""
query ListCycles($first: Int, $after: String, $filter: CycleFilter) {{
  cycles(first: $first, after: $after, filter: $filter) {{
    nodes {{ {CYCLE_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_ISSUE_STATUSES = f"""
query ListIssueStatuses($first: Int, $after: String, $filter: WorkflowStateFilter) {{
  workflowStates(first: $first, after: $after, filter: $filter) {{
    nodes {{ {WORKFLOW_STATE_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_ISSUE_LABELS = f"""
query ListIssueLabels($first: Int, $after: String, $filter: IssueLabelFilter) {{
  issueLabels(first: $first, after: $after, filter: $filter) {{
    nodes {{ {LABEL_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_COMMENTS = f"""
query ListComments($first: Int, $after: String, $filter: CommentFilter) {{
  comments(first: $first, after: $after, filter: $filter) {{
    nodes {{ {COMMENT_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_DOCUMENTS = f"""
query ListDocuments($first: Int, $after: String) {{
  documents(first: $first, after: $after) {{
    nodes {{ {DOCUMENT_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

LIST_MILESTONES = f"""
query ListMilestones($first: Int, $after: String, $filter: ProjectMilestoneFilter) {{
  projectMilestones(first: $first, after: $after, filter: $filter) {{
    nodes {{ {MILESTONE_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""


# --- Get-by-id queries ------------------------------------------------------

GET_TEAM = f"query GetTeam($id: String!) {{ team(id: $id) {{ {TEAM_FIELDS} states {{ nodes {{ {WORKFLOW_STATE_FIELDS} }} }} }} }}"
GET_USER = f"query GetUser($id: String!) {{ user(id: $id) {{ {USER_FIELDS} }} }}"
GET_PROJECT = f"query GetProject($id: String!) {{ project(id: $id) {{ {PROJECT_FIELDS} }} }}"
GET_INITIATIVE = f"query GetInitiative($id: String!) {{ initiative(id: $id) {{ {INITIATIVE_FIELDS} }} }}"
GET_ISSUE = f"query GetIssue($id: String!) {{ issue(id: $id) {{ {ISSUE_FIELDS} }} }}"
GET_MILESTONE = f"query GetMilestone($id: String!) {{ projectMilestone(id: $id) {{ {MILESTONE_FIELDS} }} }}"
GET_DOCUMENT = f"query GetDocument($id: String!) {{ document(id: $id) {{ {DOCUMENT_FIELDS} }} }}"

# Convenience: resolve an issue by its human identifier (e.g. ONDE-123).
GET_ISSUE_BY_IDENTIFIER = f"""
query GetIssueByIdentifier($team: String!, $number: Float!) {{
  issues(filter: {{ team: {{ key: {{ eq: $team }} }}, number: {{ eq: $number }} }}, first: 1) {{
    nodes {{ {ISSUE_FIELDS} }}
  }}
}}
"""


# --- Status query (workspace-level for healthcheck) -------------------------

ISSUE_STATUS_LOOKUP = """
query IssueStatus($id: String!) {
  issue(id: $id) { id identifier state { id name type color } updatedAt }
}
"""


# --- Mutations: create / update --------------------------------------------

ISSUE_CREATE = f"""
mutation IssueCreate($input: IssueCreateInput!) {{
  issueCreate(input: $input) {{
    success
    issue {{ {ISSUE_FIELDS} }}
  }}
}}
"""

ISSUE_UPDATE = f"""
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {{
  issueUpdate(id: $id, input: $input) {{
    success
    issue {{ {ISSUE_FIELDS} }}
  }}
}}
"""

ISSUE_ARCHIVE = """
mutation IssueArchive($id: String!) {
  issueArchive(id: $id) { success entity { id identifier archivedAt } }
}
"""

PROJECT_CREATE = f"""
mutation ProjectCreate($input: ProjectCreateInput!) {{
  projectCreate(input: $input) {{
    success
    project {{ {PROJECT_FIELDS} }}
  }}
}}
"""

PROJECT_UPDATE = f"""
mutation ProjectUpdate($id: String!, $input: ProjectUpdateInput!) {{
  projectUpdate(id: $id, input: $input) {{
    success
    project {{ {PROJECT_FIELDS} }}
  }}
}}
"""

PROJECT_ARCHIVE = """
mutation ProjectArchive($id: String!) {
  projectArchive(id: $id) { success entity { id name archivedAt } }
}
"""

INITIATIVE_CREATE = f"""
mutation InitiativeCreate($input: InitiativeCreateInput!) {{
  initiativeCreate(input: $input) {{
    success
    initiative {{ {INITIATIVE_FIELDS} }}
  }}
}}
"""

INITIATIVE_UPDATE = f"""
mutation InitiativeUpdate($id: String!, $input: InitiativeUpdateInput!) {{
  initiativeUpdate(id: $id, input: $input) {{
    success
    initiative {{ {INITIATIVE_FIELDS} }}
  }}
}}
"""

INITIATIVE_ARCHIVE = """
mutation InitiativeArchive($id: String!) {
  initiativeArchive(id: $id) { success entity { id name archivedAt } }
}
"""

MILESTONE_CREATE = f"""
mutation MilestoneCreate($input: ProjectMilestoneCreateInput!) {{
  projectMilestoneCreate(input: $input) {{
    success
    projectMilestone {{ {MILESTONE_FIELDS} }}
  }}
}}
"""

MILESTONE_UPDATE = f"""
mutation MilestoneUpdate($id: String!, $input: ProjectMilestoneUpdateInput!) {{
  projectMilestoneUpdate(id: $id, input: $input) {{
    success
    projectMilestone {{ {MILESTONE_FIELDS} }}
  }}
}}
"""

MILESTONE_DELETE = """
mutation MilestoneDelete($id: String!) {
  projectMilestoneDelete(id: $id) { success }
}
"""

COMMENT_CREATE = f"""
mutation CommentCreate($input: CommentCreateInput!) {{
  commentCreate(input: $input) {{
    success
    comment {{ {COMMENT_FIELDS} }}
  }}
}}
"""

COMMENT_UPDATE = f"""
mutation CommentUpdate($id: String!, $input: CommentUpdateInput!) {{
  commentUpdate(id: $id, input: $input) {{
    success
    comment {{ {COMMENT_FIELDS} }}
  }}
}}
"""

COMMENT_DELETE = """
mutation CommentDelete($id: String!) {
  commentDelete(id: $id) { success }
}
"""

DOCUMENT_CREATE = f"""
mutation DocumentCreate($input: DocumentCreateInput!) {{
  documentCreate(input: $input) {{
    success
    document {{ {DOCUMENT_FIELDS} }}
  }}
}}
"""

DOCUMENT_UPDATE = f"""
mutation DocumentUpdate($id: String!, $input: DocumentUpdateInput!) {{
  documentUpdate(id: $id, input: $input) {{
    success
    document {{ {DOCUMENT_FIELDS} }}
  }}
}}
"""

LABEL_CREATE = f"""
mutation LabelCreate($input: IssueLabelCreateInput!) {{
  issueLabelCreate(input: $input) {{
    success
    issueLabel {{ {LABEL_FIELDS} }}
  }}
}}
"""

PROJECT_UPDATE_CREATE = """
mutation ProjectUpdateCreate($input: ProjectUpdateCreateInput!) {
  projectUpdateCreate(input: $input) {
    success
    projectUpdate {
      id body health createdAt updatedAt
      url
      user { id name displayName }
      project { id name }
    }
  }
}
"""

# --- Search (workspace-scoped, real GraphQL fields) -------------------------
# Confirmed via schema introspection 2026-05-23 against api.linear.app/graphql.
# Linear exposes: searchIssues, searchDocuments, searchProjects, semanticSearch.
# There is NO `searchDocumentation` field for dev-docs search — that surface
# was removed from v0.2.0.

SEARCH_ISSUES = f"""
query SearchIssues($term: String!, $first: Int, $after: String) {{
  searchIssues(term: $term, first: $first, after: $after) {{
    nodes {{ {ISSUE_FIELDS} }}
    {PAGE_INFO}
    totalCount
  }}
}}
"""

SEARCH_DOCUMENTS = f"""
query SearchDocuments($term: String!, $first: Int, $after: String) {{
  searchDocuments(term: $term, first: $first, after: $after) {{
    nodes {{ {DOCUMENT_FIELDS} }}
    {PAGE_INFO}
    totalCount
  }}
}}
"""

SEARCH_PROJECTS = f"""
query SearchProjects($term: String!, $first: Int, $after: String) {{
  searchProjects(term: $term, first: $first, after: $after) {{
    nodes {{ {PROJECT_FIELDS} }}
    {PAGE_INFO}
    totalCount
  }}
}}
"""

# Semantic search across issues, projects, documents, comments. Returns
# heterogeneous results — node typename surfaces the entity kind.
SEMANTIC_SEARCH = """
query SemanticSearch($term: String!, $first: Int, $after: String) {
  semanticSearch(term: $term, first: $first, after: $after) {
    nodes {
      __typename
      ... on Issue { id identifier title url priorityLabel
        state { name type } team { key name } assignee { name } }
      ... on Project { id name url state }
      ... on Document { id title url }
      ... on Comment { id body url issue { identifier title } }
      ... on Initiative { id name url }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


# --- Webhooks ---------------------------------------------------------------

WEBHOOK_FIELDS = """
  id label url enabled resourceTypes allPublicTeams
  team { id key name }
  creator { id name }
  createdAt updatedAt
"""

LIST_WEBHOOKS = f"""
query ListWebhooks($first: Int, $after: String) {{
  webhooks(first: $first, after: $after) {{
    nodes {{ {WEBHOOK_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

GET_WEBHOOK = f"query GetWebhook($id: String!) {{ webhook(id: $id) {{ {WEBHOOK_FIELDS} }} }}"

WEBHOOK_CREATE = f"""
mutation WebhookCreate($input: WebhookCreateInput!) {{
  webhookCreate(input: $input) {{
    success
    webhook {{ {WEBHOOK_FIELDS} }}
  }}
}}
"""

WEBHOOK_UPDATE = f"""
mutation WebhookUpdate($id: String!, $input: WebhookUpdateInput!) {{
  webhookUpdate(id: $id, input: $input) {{
    success
    webhook {{ {WEBHOOK_FIELDS} }}
  }}
}}
"""

WEBHOOK_DELETE = """
mutation WebhookDelete($id: String!) {
  webhookDelete(id: $id) { success }
}
"""


# --- Notifications (inbox) --------------------------------------------------

NOTIFICATION_FIELDS = """
  id type emailedAt readAt snoozedUntilAt unsnoozedAt
  user { id name displayName }
  actor { id name displayName }
  externalUserActor { id name }
  ... on IssueNotification {
    issue { id identifier title url state { name } }
    team { id key name }
    comment { id body url }
  }
  ... on ProjectNotification {
    project { id name url }
  }
  ... on OauthClientApprovalNotification {
    oauthClientApproval { id }
  }
"""

LIST_NOTIFICATIONS = f"""
query ListNotifications($first: Int, $after: String, $filter: NotificationFilter) {{
  notifications(first: $first, after: $after, filter: $filter) {{
    nodes {{
      __typename
      {NOTIFICATION_FIELDS}
    }}
    {PAGE_INFO}
    totalCount
  }}
}}
"""

GET_NOTIFICATION = f"""
query GetNotification($id: String!) {{
  notification(id: $id) {{
    __typename
    {NOTIFICATION_FIELDS}
  }}
}}
"""

NOTIFICATIONS_UNREAD_COUNT = """
query NotificationsUnreadCount {
  notificationsUnreadCount
}
"""

NOTIFICATION_MARK_READ = """
mutation NotificationUpdate($id: String!, $input: NotificationUpdateInput!) {
  notificationUpdate(id: $id, input: $input) {
    success
    notification { id readAt }
  }
}
"""

NOTIFICATION_MARK_READ_ALL = """
mutation NotificationMarkReadAll($input: NotificationUpdateAllInput!) {
  notificationMarkReadAll(input: $input) { success }
}
"""

NOTIFICATION_ARCHIVE = """
mutation NotificationArchive($id: String!) {
  notificationArchive(id: $id) { success entity { id archivedAt } }
}
"""


# --- Attachments ------------------------------------------------------------

ATTACHMENT_FIELDS = """
  id title subtitle url source sourceType groupBySource metadata
  issue { id identifier title }
  creator { id name displayName }
  createdAt updatedAt
"""

LIST_ATTACHMENTS_FOR_ISSUE = f"""
query AttachmentsForIssue($issue_id: String!, $first: Int, $after: String) {{
  attachments(filter: {{ issue: {{ id: {{ eq: $issue_id }} }} }}, first: $first, after: $after) {{
    nodes {{ {ATTACHMENT_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

ATTACHMENTS_FOR_URL = f"""
query AttachmentsForURL($url: String!, $first: Int) {{
  attachmentsForURL(url: $url, first: $first) {{
    nodes {{ {ATTACHMENT_FIELDS} }}
  }}
}}
"""

GET_ATTACHMENT = f"query GetAttachment($id: String!) {{ attachment(id: $id) {{ {ATTACHMENT_FIELDS} }} }}"

ATTACHMENT_LINK_URL = f"""
mutation AttachmentLinkURL(
  $issueId: String!, $url: String!, $title: String, $iconUrl: String
) {{
  attachmentLinkURL(issueId: $issueId, url: $url, title: $title, iconUrl: $iconUrl) {{
    success
    attachment {{ {ATTACHMENT_FIELDS} }}
  }}
}}
"""

ATTACHMENT_DELETE = """
mutation AttachmentDelete($id: String!) {
  attachmentDelete(id: $id) { success }
}
"""


# --- Issue relations (blocks / blocked-by / duplicates / related) -----------

RELATION_FIELDS = """
  id type
  issue { id identifier title state { id name type color } }
  relatedIssue { id identifier title state { id name type color } }
  createdAt updatedAt
"""

LIST_ISSUE_RELATIONS = f"""
query ListIssueRelations($first: Int, $after: String) {{
  issueRelations(first: $first, after: $after) {{
    nodes {{ {RELATION_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

GET_ISSUE_RELATIONS = f"""
query GetIssueRelations($id: String!, $first: Int, $after: String) {{
  issue(id: $id) {{
    id identifier title
    relations(first: $first, after: $after) {{
      nodes {{ {RELATION_FIELDS} }}
      {PAGE_INFO}
    }}
    inverseRelations(first: $first, after: $after) {{
      nodes {{ {RELATION_FIELDS} }}
      {PAGE_INFO}
    }}
  }}
}}
"""

ISSUE_RELATION_CREATE = f"""
mutation IssueRelationCreate($input: IssueRelationCreateInput!) {{
  issueRelationCreate(input: $input) {{
    success
    issueRelation {{ {RELATION_FIELDS} }}
  }}
}}
"""

ISSUE_RELATION_DELETE = """
mutation IssueRelationDelete($id: String!) {
  issueRelationDelete(id: $id) { success }
}
"""


# --- Agent sessions ---------------------------------------------------------

AGENT_SESSION_FIELDS = """
  id status type startedAt endedAt
  issue { id identifier title }
  comment { id body url }
  creator { id name displayName }
  appUser { id name displayName }
  createdAt updatedAt
"""

LIST_AGENT_SESSIONS = f"""
query ListAgentSessions($first: Int, $after: String, $filter: AgentSessionFilter) {{
  agentSessions(first: $first, after: $after, filter: $filter) {{
    nodes {{ {AGENT_SESSION_FIELDS} }}
    {PAGE_INFO}
  }}
}}
"""

GET_AGENT_SESSION = f"""
query GetAgentSession($id: String!) {{
  agentSession(id: $id) {{ {AGENT_SESSION_FIELDS} }}
}}
"""

AGENT_SESSION_CREATE_ON_ISSUE = f"""
mutation AgentSessionCreateOnIssue($input: AgentSessionCreateOnIssueInput!) {{
  agentSessionCreateOnIssue(input: $input) {{
    success
    agentSession {{ {AGENT_SESSION_FIELDS} }}
  }}
}}
"""

AGENT_SESSION_CREATE_ON_COMMENT = f"""
mutation AgentSessionCreateOnComment($input: AgentSessionCreateOnCommentInput!) {{
  agentSessionCreateOnComment(input: $input) {{
    success
    agentSession {{ {AGENT_SESSION_FIELDS} }}
  }}
}}
"""


# --- Bulk operations --------------------------------------------------------

ISSUE_BATCH_UPDATE = f"""
mutation IssueBatchUpdate($ids: [UUID!]!, $input: IssueUpdateInput!) {{
  issueBatchUpdate(ids: $ids, input: $input) {{
    success
    issues {{ {ISSUE_FIELDS} }}
  }}
}}
"""
