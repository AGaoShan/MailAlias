export function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`;
}

export function sessionStateText(state: string): string {
  const map: Record<string, string> = {
    unknown: "未检测",
    logging_in: "登录中",
    active: "登录成功",
    expired: "登录过期",
    error: "登录失败",
    // 兼容旧值
    none: "未检测",
  };
  return map[state] ?? state;
}

export function sessionStateType(state: string): "success" | "warning" | "danger" | "info" {
  const map: Record<string, "success" | "warning" | "danger" | "info"> = {
    unknown: "info",
    logging_in: "warning",
    active: "success",
    expired: "warning",
    error: "danger",
    none: "info",
  };
  return map[state] ?? "info";
}

/** 状态是否表示会话可用 */
export function isSessionUsable(state: string): boolean {
  return state === "active";
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  }
}
