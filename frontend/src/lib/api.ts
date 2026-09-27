const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const ACCESS_KEY = "aula.access_token";
const MUST_CHANGE_KEY = "aula.must_change";
const ROLE_KEY = "aula.role";

export type SessionRole = "student" | "staff";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function mustChangeCredentials(): boolean {
  return localStorage.getItem(MUST_CHANGE_KEY) === "1";
}

export function getSessionRole(): SessionRole | null {
  const role = localStorage.getItem(ROLE_KEY);
  return role === "student" || role === "staff" ? role : null;
}

export function setSession(
  tokens: {
    access_token: string;
    must_change_credentials: boolean;
  },
  role: SessionRole,
): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(MUST_CHANGE_KEY, tokens.must_change_credentials ? "1" : "0");
  localStorage.setItem(ROLE_KEY, role);
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(MUST_CHANGE_KEY);
  localStorage.removeItem(ROLE_KEY);
}

async function parseError(response: Response): Promise<string> {
  let detail = response.statusText || "Error";
  try {
    const body = (await response.json()) as { detail?: string | { msg?: string }[] };
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail))
      detail = body.detail.map((d) => d.msg ?? "invalid").join("; ");
  } catch {
    // sin cuerpo JSON
  }
  return detail;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE}${path}`, {
    headers,
    credentials: "include",
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  return (await response.json()) as T;
}

export async function apiSend<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  return (await response.json()) as T;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    credentials: "include",
    body: form,
  });
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  return (await response.json()) as T;
}

export type HealthPayload = {
  status: string;
  app: string;
  version: string;
  time: string;
};

export type TokenPayload = {
  access_token: string;
  token_type: string;
  must_change_credentials: boolean;
  /** Reto 2FA de super_admin (Fase D): no hay sesión hasta verificar. */
  mfa_required?: boolean;
  mfa_token?: string | null;
  mfa_enrolled?: boolean;
};

export type MfaSetupResponse = {
  secret: string;
  otpauth_url: string;
  mfa_enabled: boolean;
};

export type MfaVerifyResponse = {
  mfa_enabled: boolean;
  access_token: string | null;
  token_type: string;
  must_change_credentials: boolean | null;
};

export type PlanPublic = {
  id: string;
  name: string;
  description: string;
  price_eur: number;
  max_courses: number | null;
  currency: string;
  interval: string;
};

export type OrganizationRegisterResponse = {
  organization_id: number;
  checkout_url: string;
};

export type ActivationInfo = {
  email: string;
  expires_at: string | null;
};

export type ActivationDone = {
  status: string;
  email: string;
};

export type OrgStatus = "pending_payment" | "trialing" | "active" | "past_due" | "canceled";

export type OrganizationAdminPublic = {
  id: number;
  name: string;
  tax_id: string;
  billing_email: string;
  status: OrgStatus;
  plan_id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  trial_ends_at: string | null;
  created_at: string;
  user_count: number;
  course_count: number;
};

export type SubscriptionRow = {
  organization_id: number;
  organization_name: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  status: OrgStatus;
  plan_id: string;
  trial_ends_at: string | null;
};

export type PlatformMetrics = {
  orgs_by_status: Record<string, number>;
  orgs_by_plan: Record<string, number>;
  users_by_role: Record<string, number>;
  total_courses: number;
  trials_ending_soon: number;
};

export type CoursePublic = {
  id: number;
  name: string;
  description: string | null;
  code: string;
  status: "active" | "archived";
  layout_rows: number;
  layout_cols: number;
  settings: Record<string, unknown>;
  category_id: number | null;
  cohort_id: number | null;
  created_at: string;
};

export type ClassroomSeat = {
  seat_id: number;
  row: number;
  col: number;
  enrollment_id: number | null;
  student_id: number | null;
  student_name: string | null;
  student_username: string | null;
  status: string | null;
};

export type ClassroomPayload = {
  course: CoursePublic;
  seats: ClassroomSeat[];
  rows: number;
  cols: number;
  teachers: { id: number; name: string }[];
};

export type AssignmentPublic = {
  id: number;
  course_id: number;
  section_id: number | null;
  title: string;
  description_markdown: string;
  due_at: string | null;
  max_score: string;
  visibility: string;
  rubric_id: number | null;
  created_by: number;
  created_at: string;
};

export type EvaluationPublic = {
  id: number;
  submission_id: number;
  teacher_id: number;
  score: string | null;
  rubric_scores: Record<string, unknown>;
  comment_markdown: string;
  created_at: string;
};

export type SubmissionFilePublic = {
  id: number;
  original_name: string;
  mime: string;
  size_bytes: number;
  sha256: string;
};

export type SubmissionPublic = {
  id: number;
  assignment_id: number | null;
  course_id: number;
  student_id: number;
  github_url: string | null;
  notes: string;
  status: string;
  submitted_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  files: SubmissionFilePublic[];
  latest_evaluation: EvaluationPublic | null;
  evaluations: EvaluationPublic[];
  student_name: string | null;
};

export type EnrollmentPublic = {
  id: number;
  course_id: number;
  student_id: number;
  seat_id: number | null;
  status: string;
  student_name: string | null;
  student_username: string | null;
  seat_row: number | null;
  seat_col: number | null;
};

export type SectionKind = "content" | "external";

export type SectionPublic = {
  id: number;
  course_id: number;
  title: string;
  slug: string;
  order: number;
  kind: SectionKind;
  body_markdown: string | null;
  external_url: string | null;
};

export type AnnouncementPublic = {
  id: number;
  course_id: number;
  author_id: number;
  title: string;
  body_markdown: string;
  created_at: string;
  author_name: string | null;
};

export type UserPublic = {
  id: number;
  name: string;
  email: string | null;
  username: string | null;
  role: "super_admin" | "org_admin" | "teacher" | "student";
  is_active: boolean;
  must_change_credentials: boolean;
  mfa_enabled: boolean;
  created_at: string;
};

export type AdminUserPublic = UserPublic;

export type PinResetResponse = {
  user_id: number;
  pin: string;
  must_change_credentials: boolean;
};

export type CsvImportResult = {
  created: number;
  skipped: number;
  pins: Record<string, string>;
};

export type AuditLogPublic = {
  id: number;
  actor_id: number | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  course_id: number | null;
  payload: Record<string, unknown>;
  ip: string | null;
  created_at: string;
  actor_name: string | null;
};

export type RubricCriterion = {
  id: string;
  label: string;
  max: number;
};

export type RubricPublic = {
  id: number;
  course_id: number;
  title: string;
  criteria: RubricCriterion[];
  created_by: number;
  created_at: string;
};

export type AttendanceStatus = "present" | "late" | "absent" | "excused";

export type AttendanceRecordPublic = {
  id: number;
  course_id: number;
  student_id: number;
  date: string;
  status: AttendanceStatus;
  student_name: string | null;
  student_username: string | null;
  seat_row: number | null;
  seat_col: number | null;
};

export type AttendanceDayResponse = {
  date: string;
  records: AttendanceRecordPublic[];
};

export type AttendanceSummaryItem = {
  student_id: number;
  student_name: string | null;
  student_username: string | null;
  present: number;
  late: number;
  absent: number;
  excused: number;
};

export type CalendarEvent = {
  kind: "assignment" | "announcement";
  id: number;
  title: string;
  starts_at: string | null;
  ends_at: string | null;
  body_markdown: string | null;
};

export type GithubMetaResponse = {
  url: string;
  full_name: string | null;
  description: string | null;
  language: string | null;
  default_branch: string | null;
  stars: number | null;
  pushed_at: string | null;
  html_url: string | null;
  cached: boolean;
  ok: boolean;
  error: string | null;
};

export type RgpdExportResponse = {
  user: Record<string, unknown>;
  enrollments: unknown[];
  submissions: unknown[];
  evaluations: unknown[];
  attendance: unknown[];
  exported_at: string;
};

export type AdminDashboardStats = {
  courses_total: number;
  courses_active: number;
  users_total: number;
  students_total: number;
  teachers_total: number;
  enrollments_total: number;
  submissions_pending: number;
  submissions_total: number;
  recent_audit: {
    id: number;
    action: string;
    actor_name: string | null;
    course_id: number | null;
    created_at: string;
  }[];
  recent_submissions: {
    id: number;
    student_name: string | null;
    course_name: string | null;
    status: string;
    updated_at: string;
  }[];
};

export type AdminUserCreated = AdminUserPublic & {
  temporary_secret: string | null;
};

export type StaffPasswordResetResponse = {
  user_id: number;
  password: string;
  must_change_credentials: boolean;
};

export type ObserverSubmissionRow = {
  id: number;
  course_id: number;
  course_name: string;
  course_code: string;
  student_id: number;
  student_name: string | null;
  student_username: string | null;
  assignment_id: number | null;
  assignment_title: string | null;
  status: string;
  version: number;
  github_url: string | null;
  notes: string;
  submitted_at: string | null;
  updated_at: string;
  file_count: number;
  files: { id: number; original_name: string; mime: string; size_bytes: number }[];
  latest_score: string | null;
  latest_comment: string | null;
  evaluated_at: string | null;
};

export type ObserverResponse = {
  total: number;
  items: ObserverSubmissionRow[];
};

export type MessagePublic = {
  id: number;
  sender_id: number;
  recipient_id: number;
  course_id: number | null;
  body: string;
  read_at: string | null;
  created_at: string;
  sender_name: string | null;
  recipient_name: string | null;
};

export type ConversationSummary = {
  user_id: number;
  name: string;
  role: string;
  username: string | null;
  email: string | null;
  last_message: string;
  last_at: string;
  unread_count: number;
};

export type MessageDirectoryEntry = {
  id: number;
  name: string;
  role: string;
  username: string | null;
  email: string | null;
  course_ids: number[];
};

export type UnreadCountResponse = {
  private: number;
  courses: Record<string, number>;
  total: number;
};

export type CourseMessagePublic = {
  id: number;
  course_id: number;
  sender_id: number;
  body: string;
  created_at: string;
  sender_name: string | null;
  sender_role: string | null;
};

export type CourseChatPage = {
  total: number;
  unread: number;
  items: CourseMessagePublic[];
};

export type CourseChatRoomSummary = {
  course_id: number;
  course_name: string;
  course_code: string;
  unread: number;
  last_message: string | null;
  last_at: string | null;
  last_sender_name: string | null;
};

export type MultiCourseRow = {
  course_id: number;
  name: string;
  code: string;
  status: string;
  enrolled: number;
  assignments: number;
  submissions_total: number;
  submissions_pending: number;
  completion_rate: number;
};

export type MultiCourseDashboard = {
  totals: Record<string, number>;
  courses: MultiCourseRow[];
};

export type GradebookCell = {
  assignment_id: number | null;
  status: string | null;
  score: string | null;
};

export type GradebookColumn = {
  assignment_id: number;
  title: string;
  max_score: string;
};

export type GradebookStudent = {
  student_id: number;
  name: string;
  username: string | null;
  cells: Record<string, GradebookCell>;
  average: string | null;
};

export type GradebookMatrix = {
  course_id: number;
  course_name: string;
  columns: GradebookColumn[];
  students: GradebookStudent[];
};

export type CenterSettings = {
  center_name: string;
  support_email: string | null;
  default_visibility: string;
  allow_peer_submissions: boolean;
  pin_length: number;
  max_upload_mb: number;
  terms_markdown: string;
};

export type ReportCourseRow = {
  course_id: number;
  name: string;
  code: string;
  status: string;
  enrolled: number;
  assignments: number;
  submissions: number;
  reviewed: number;
  avg_score: number | null;
  attendance_present: number;
  attendance_absent: number;
};

export type ReportOverview = {
  generated_at: string;
  center_name: string;
  totals: Record<string, number>;
  courses: ReportCourseRow[];
};

export type InstitutionalCalendarItem = {
  kind: string;
  id: number;
  title: string;
  course_id: number;
  course_name: string;
  course_code: string;
  starts_at: string | null;
  ends_at: string | null;
};

export type CourseBackup = {
  exported_at: string;
  course: Record<string, unknown>;
  seats: unknown[];
  teachers: { teacher_id: number; name: string | null }[];
  enrollments: unknown[];
  sections: unknown[];
  rubrics: unknown[];
  assignments: unknown[];
  announcements: unknown[];
  submissions: unknown[];
};

export type CategoryPublic = {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  course_count: number;
};

export type CohortPublic = {
  id: number;
  name: string;
  code: string;
  category_id: number | null;
  created_at: string;
  member_count: number;
};

export type CohortMemberPublic = {
  student_id: number;
  name: string;
  username: string | null;
};

export type CohortDetail = CohortPublic & {
  members: CohortMemberPublic[];
};

export type CustomRolePublic = {
  id: number;
  name: string;
  permissions: string[];
  created_at: string;
  assigned_count: number;
};

export type PermissionCatalog = {
  permissions: string[];
  effective: string[];
};

export type ActiveSessionPublic = {
  id: number;
  user_id: number;
  user_name: string;
  user_role: string;
  created_at: string;
  expires_at: string;
};

export type AutoEnrollResult = {
  enrolled: number;
  skipped: number;
  reason: string | null;
};

export type CourseTaxonomyPublic = {
  course_id: number;
  category_id: number | null;
  cohort_id: number | null;
};

export type TeacherTotals = {
  courses_count: number;
  students_count: number;
  pending_evaluations: number;
  due_this_week: number;
  open_assignments: number;
};

export type TeacherDashboardCourse = {
  id: number;
  name: string;
  code: string;
  status: string;
  students: number;
  pending: number;
  open_assignments: number;
  next_due_at: string | null;
};

export type TeacherUpcomingItem = {
  course_id: number;
  course_name: string;
  assignment_id: number;
  title: string;
  due_at: string;
};

export type TeacherRecentItem = {
  course_id: number;
  course_name: string;
  assignment_title: string | null;
  student_name: string;
  status: string;
  submitted_at: string | null;
};

export type TeacherDashboard = {
  totals: TeacherTotals;
  courses: TeacherDashboardCourse[];
  upcoming: TeacherUpcomingItem[];
  recent: TeacherRecentItem[];
};

export type StudentTotals = {
  courses_count: number;
  pending_submissions: number;
  due_this_week: number;
  graded_submissions: number;
};

export type StudentDashboardCourse = {
  id: number;
  name: string;
  code: string;
  status: string;
  pending: number;
  next_due_at: string | null;
};

export type StudentUpcomingItem = {
  course_id: number;
  course_name: string;
  assignment_id: number;
  title: string;
  due_at: string;
};

export type StudentRecentEvaluation = {
  course_id: number;
  course_name: string;
  assignment_id: number | null;
  assignment_title: string | null;
  score: number | null;
  evaluated_at: string | null;
};

export type StudentPendingItem = {
  course_id: number;
  course_name: string;
  assignment_id: number;
  title: string;
  due_at: string | null;
};

export type StudentDashboard = {
  totals: StudentTotals;
  courses: StudentDashboardCourse[];
  upcoming: StudentUpcomingItem[];
  recent: StudentRecentEvaluation[];
  pending_items: StudentPendingItem[];
};

export type StudentAssignmentProgress = {
  assignment_id: number;
  title: string;
  due_at: string | null;
  status: string;
  score: number | null;
  submitted_at: string | null;
};

export type StudentProgressSummary = {
  total: number;
  delivered: number;
  pending: number;
  average_score: number | null;
  delivery_pct: number;
};

export type StudentAttendanceSummary = {
  present: number;
  late: number;
  absent: number;
  excused: number;
  pct: number | null;
};

export type StudentCourseProgress = {
  course_id: number;
  course_name: string;
  assignment_stats: StudentAssignmentProgress[];
  summary: StudentProgressSummary;
  attendance: StudentAttendanceSummary;
};

export type TeacherQueueItem = {
  submission_id: number;
  course_id: number;
  course_name: string;
  assignment_id: number | null;
  assignment_title: string | null;
  student_id: number;
  student_name: string;
  status: string;
  submitted_at: string | null;
  due_at: string | null;
};

export type TeacherQueuePage = {
  items: TeacherQueueItem[];
  total: number;
  page: number;
  page_size: number;
};

export type PendingCount = {
  pending: number;
};

export type CourseAssignmentStat = {
  assignment_id: number;
  title: string;
  submitted: number;
  total: number;
  pct: number;
};

export type CourseStudentStat = {
  student_id: number;
  name: string;
  submitted: number;
  pending: number;
  last_score: number | null;
  attendance_pct: number | null;
};

export type CourseOverview = {
  course_id: number;
  course_name: string;
  assignment_stats: CourseAssignmentStat[];
  student_stats: CourseStudentStat[];
};

export type StudentSubmissionRow = {
  submission_id: number;
  assignment_id: number | null;
  assignment_title: string | null;
  status: string;
  submitted_at: string | null;
  score: number | null;
  evaluated_at: string | null;
};

export type StudentAttendance = {
  present: number;
  late: number;
  absent: number;
  excused: number;
  pct: number | null;
};

export type StudentCourseDetail = {
  student_id: number;
  name: string;
  username: string | null;
  course_id: number;
  course_name: string;
  submitted: number;
  pending: number;
  average_score: number | null;
  attendance: StudentAttendance;
  submissions: StudentSubmissionRow[];
};

export async function apiDownload(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE}${path}`, { headers, credentials: "include" });
  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
