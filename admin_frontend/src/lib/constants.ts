import {
  ClipboardCheck,
  FileUp,
  LayoutDashboard,
  Search,
  Sparkles,
  Upload,
  UsersRound,
} from "lucide-react";

export const adminNavItems = [
  { href: "/hr/tasks", label: "任务执行", icon: LayoutDashboard },
  { href: "/hr/workbench", label: "推荐处理台", icon: Sparkles },
  { href: "/hr/checklist", label: "Checklist", icon: ClipboardCheck },
  { href: "/hr/search", label: "高级搜索", icon: Search },
  { href: "/hr/phase2", label: "JD评分卡", icon: Upload },
  { href: "/hr/resume-imports", label: "简历导入", icon: FileUp },
  { href: "/hr/users", label: "用户管理", icon: UsersRound, adminOnly: true },
];

export const stageLabels: Record<string, string> = {
  new: "新入库",
  scored: "已评分",
  to_review: "待复核",
  to_contact: "建议沟通",
  contacted: "已沟通",
  awaiting_reply: "待回复",
  needs_followup: "待跟进",
  interview_invited: "已邀约",
  interview_scheduled: "面试已约",
  talent_pool: "人才库",
  rejected: "已淘汰",
  do_not_contact: "不再联系",
};

export const reasonCodeLabels: Record<string, string> = {
  skills_match: "技能匹配",
  skills_gap: "技能不匹配",
  industry_fit: "行业匹配",
  industry_gap: "行业不匹配",
  years_gap: "年限不足",
  education_gap: "学历不符",
  salary_gap: "薪资不符",
  city_gap: "城市不符",
  resume_incomplete: "简历信息待补充",
  candidate_positive: "候选人意向积极",
  reusable_pool: "适合沉淀人才库",
  duplicate_candidate: "重复候选人",
  do_not_contact: "不再联系",
};

export const finalDecisionLabels: Record<string, string> = {
  recommend: "建议沟通",
  review: "继续复核",
  reject: "暂不沟通",
  talent_pool: "沉淀人才库",
  pending: "待处理",
};

export const systemDecisionLabels: Record<string, string> = {
  recommend: "建议沟通",
  review: "继续复核",
  reject: "暂不沟通",
};

export const candidateActionStatusLabels: Record<string, string> = {
  success: "成功",
  skipped: "已跳过",
  failed: "失败",
};
