import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./layout";
import { HomePage } from "../features/home/HomePage";
import { NotFoundPage } from "./NotFoundPage";
import { LoginPage } from "../features/auth/LoginPage";
import { ChangeCredentialsPage } from "../features/auth/ChangeCredentialsPage";
import { useAuth } from "../features/auth/AuthContext";
import { usePermissions } from "../features/auth/usePermissions";
import { CourseListPage } from "../features/courses/CourseListPage";
import { ClassroomPage } from "../features/courses/ClassroomPage";
import { ContentPage } from "../features/content/ContentPage";
import { WorkPage } from "../features/work/WorkPage";
import { AssignmentDetailPage } from "../features/work/AssignmentDetailPage";
import { EvaluatePage } from "../features/work/EvaluatePage";
import { AttendancePage } from "../features/attendance/AttendancePage";
import { CalendarPage } from "../features/calendar/CalendarPage";
import { RubricsPage } from "../features/rubrics/RubricsPage";
import { AccountPrivacyPage } from "../features/account/AccountPrivacyPage";
import { AccountSettingsPage } from "../features/account/AccountSettingsPage";
import { MessagesPage } from "../features/messages/MessagesPage";
import { PrivateMessagesPage } from "../features/messages/private/PrivateMessagesPage";
import { CourseMessagesPage } from "../features/messages/course/CourseMessagesPage";
import { MultiCourseDashboardPage } from "../features/phasec/MultiCourseDashboardPage";
import { CenterSettingsPage } from "../features/phasec/CenterSettingsPage";
import { ReportsPage } from "../features/phasec/ReportsPage";
import { GradebookPage } from "../features/phasec/GradebookPage";
import { InstitutionalCalendarPage } from "../features/phasec/InstitutionalCalendarPage";
import { CategoriesPage } from "../features/scale/CategoriesPage";
import { CohortsPage } from "../features/scale/CohortsPage";
import { RolesPage } from "../features/scale/RolesPage";
import { SessionsPage } from "../features/scale/SessionsPage";
import { AdminLayout } from "../features/admin/AdminLayout";
import { PreciosPage } from "../features/public/PreciosPage";
import { RegistroEmpresaPage } from "../features/public/RegistroEmpresaPage";
import { ActivarCuentaPage } from "../features/public/ActivarCuentaPage";
import { PlatformAccessPage } from "../features/superadmin/PlatformAccessPage";
import { SuperAdminLayout } from "../features/superadmin/SuperAdminLayout";
import { PlatformMetricsPage } from "../features/superadmin/PlatformMetricsPage";
import { OrganizationsPage } from "../features/superadmin/OrganizationsPage";
import { SubscriptionsPage } from "../features/superadmin/SubscriptionsPage";
import { MfaSettingsPage } from "../features/superadmin/MfaSettingsPage";
import { TeacherLayout } from "../features/teacher/TeacherLayout";
import { StudentLayout } from "../features/student/StudentLayout";
import { StudentDashboardPage } from "../features/student/dashboard/StudentDashboardPage";
import { MyProgressPage } from "../features/student/course/MyProgressPage";
import { TeacherDashboardPage } from "../features/teacher/dashboard/TeacherDashboardPage";
import { EvaluationQueuePage } from "../features/teacher/queue/EvaluationQueuePage";
import { TeacherCourseOverviewPage } from "../features/teacher/course/TeacherCourseOverviewPage";
import { StudentDetailPage } from "../features/teacher/course/StudentDetailPage";
import { AdminDashboardPage } from "../features/admin/dashboard/AdminDashboardPage";
import { AdminCoursesPage } from "../features/admin/courses/AdminCoursesPage";
import { AdminCourseDetailPage } from "../features/admin/courses/AdminCourseDetailPage";
import { AdminUsersPage } from "../features/admin/users/AdminUsersPage";
import { AdminObserverPage } from "../features/admin/observer/AdminObserverPage";
import { AdminAuditPage } from "../features/admin/audit/AdminAuditPage";
import { ImportCsvPage } from "../features/admin/import/ImportCsvPage";
import { AdminToolsPage } from "../features/admin/tools/AdminToolsPage";
import { Spinner } from "../components/ui/Spinner";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, mustChange } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location }} />;
  if (mustChange) return <Navigate to="/change-credentials" replace />;
  return children;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "org_admin") return <Navigate to="/" replace />;
  return children;
}

function RequireTeacher({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "teacher" && user.role !== "org_admin")
    return <Navigate to="/" replace />;
  return children;
}

function RequireStudent({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "student" && user.role !== "org_admin")
    return <Navigate to="/" replace />;
  return children;
}

function RequireStaff({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role === "student") return <Navigate to="/student" replace />;
  return children;
}

function RequireSuperAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "super_admin") return <Navigate to="/" replace />;
  return children;
}

function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { user } = useAuth();
  const permissions = usePermissions();
  if (user && user.role === "org_admin") return children;
  if (permissions.isPending) return <Spinner label="Comprobando permisos…" />;
  const effective = permissions.data?.effective ?? [];
  if (permissions.isError || !effective.includes(permission)) return <Navigate to="/" replace />;
  return children;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/change-credentials" element={<ChangeCredentialsPage />} />
        <Route path="/precios" element={<PreciosPage />} />
        <Route path="/registro-empresa" element={<RegistroEmpresaPage />} />
        <Route path="/activar-cuenta/:token" element={<ActivarCuentaPage />} />
        <Route path="/plataforma/acceso" element={<PlatformAccessPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <HomePage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses"
          element={
            <RequireAuth>
              <CourseListPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId"
          element={
            <RequireAuth>
              <ClassroomPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/content"
          element={
            <RequireAuth>
              <ContentPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/work"
          element={
            <RequireAuth>
              <WorkPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/work/:assignmentId"
          element={
            <RequireAuth>
              <AssignmentDetailPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/evaluate"
          element={
            <RequireAuth>
              <RequireStaff>
                <EvaluatePage />
              </RequireStaff>
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/attendance"
          element={
            <RequireAuth>
              <RequireStaff>
                <AttendancePage />
              </RequireStaff>
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/calendar"
          element={
            <RequireAuth>
              <CalendarPage />
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/rubrics"
          element={
            <RequireAuth>
              <RequireStaff>
                <RubricsPage />
              </RequireStaff>
            </RequireAuth>
          }
        />
        <Route
          path="/courses/:courseId/gradebook"
          element={
            <RequireAuth>
              <RequireStaff>
                <GradebookPage />
              </RequireStaff>
            </RequireAuth>
          }
        />
        <Route
          path="/calendar"
          element={
            <RequireAuth>
              <InstitutionalCalendarPage />
            </RequireAuth>
          }
        />
        <Route
          path="/account"
          element={
            <RequireAuth>
              <AccountSettingsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/account/privacy"
          element={
            <RequireAuth>
              <AccountPrivacyPage />
            </RequireAuth>
          }
        />
        <Route
          path="/messages"
          element={
            <RequireAuth>
              <MessagesPage />
            </RequireAuth>
          }
        >
          <Route index element={<PrivateMessagesPage />} />
          <Route path="course" element={<CourseMessagesPage />} />
        </Route>
        <Route
          path="/admin"
          element={
            <RequireAuth>
              <RequireAdmin>
                <AdminLayout />
              </RequireAdmin>
            </RequireAuth>
          }
        >
          <Route index element={<AdminDashboardPage />} />
          <Route path="multi" element={<MultiCourseDashboardPage />} />
          <Route path="courses" element={<AdminCoursesPage />} />
          <Route path="courses/:courseId" element={<AdminCourseDetailPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="messages" element={<Navigate to="/messages" replace />} />
          <Route path="observer" element={<AdminObserverPage />} />
          <Route path="audit" element={<AdminAuditPage />} />
          <Route path="import" element={<ImportCsvPage />} />
          <Route path="tools" element={<AdminToolsPage />} />
          <Route path="settings" element={<CenterSettingsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="cohorts" element={<CohortsPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="sessions" element={<SessionsPage />} />
        </Route>
        <Route
          path="/admin/reports"
          element={
            <RequireAuth>
              <RequirePermission permission="reports.view">
                <AdminLayout />
              </RequirePermission>
            </RequireAuth>
          }
        >
          <Route index element={<ReportsPage />} />
        </Route>
        <Route
          path="/teacher"
          element={
            <RequireAuth>
              <RequireTeacher>
                <TeacherLayout />
              </RequireTeacher>
            </RequireAuth>
          }
        >
          <Route index element={<TeacherDashboardPage />} />
          <Route path="queue" element={<EvaluationQueuePage />} />
          <Route path="courses/:courseId" element={<TeacherCourseOverviewPage />} />
          <Route path="courses/:courseId/students/:studentId" element={<StudentDetailPage />} />
        </Route>
        <Route
          path="/student"
          element={
            <RequireAuth>
              <RequireStudent>
                <StudentLayout />
              </RequireStudent>
            </RequireAuth>
          }
        >
          <Route index element={<StudentDashboardPage />} />
          <Route path="courses/:courseId" element={<MyProgressPage />} />
        </Route>
        <Route
          path="/plataforma"
          element={
            <RequireAuth>
              <RequireSuperAdmin>
                <SuperAdminLayout />
              </RequireSuperAdmin>
            </RequireAuth>
          }
        >
          <Route index element={<PlatformMetricsPage />} />
          <Route path="organizaciones" element={<OrganizationsPage />} />
          <Route path="suscripciones" element={<SubscriptionsPage />} />
          <Route path="2fa" element={<MfaSettingsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
