const API = process.env.NEXT_PUBLIC_TRAINING_API_URL ?? "http://127.0.0.1:8100/api";
const headers = {"Content-Type": "application/json", "X-Training-User-Id": "demo-user"};

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {...options, headers: {...headers, ...options?.headers}, cache: "no-store"});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `请求失败（${response.status}）`);
  }
  return response.json();
}

export type Option = {department_id: string; name: string};
export type Question = {id: string; case_origin: string; case_content: string; options: Option[]};
export type Attempt = {attempt_id: string; mode: "challenge" | "practice"; level?: number; practice_cycle?: number; questions: Question[]};
export type Evidence = {title?:string; source?:string; excerpt?:string; locator?:string; reason?:string};
export type Feedback = {is_correct: boolean; selected_department: string; correct_department: Option; explanation: string; reference_basis: string; reference_basis_detail?:Evidence};
export type PracticeProgress = {cycle:number; completed_count:number; remaining_count:number; total_count:number};
