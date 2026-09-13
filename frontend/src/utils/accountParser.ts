export interface ParsedAccount {
  email: string;
  password: string;
}

export interface ParseResult {
  accounts: ParsedAccount[];
  invalid: string[];
}

/**
 * 解析单行账号文本，支持以下分隔符（两边允许有空格）：
 *   ------------
 *   email----password
 *   email:password（冒号/中文冒号/制表符/竖线/逗号/空格）
 * 返回 null 表示无法解析或格式不合法。
 */
export function parseAccountLine(line: string): ParsedAccount | null {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) return null;

  const patterns: RegExp[] = [
    /\s*----\s*/,
    /\t+/,
    /\|+/,
    /\s*[:：]\s*/,
    /\s*,\s*/,
    /\s+/,
  ];

  for (const pattern of patterns) {
    const parts = trimmed.split(pattern);
    if (parts.length >= 2) {
      const email = (parts.shift() ?? "").trim();
      const password = parts.join(" ").trim();
      if (isValidEmail(email) && password) {
        return { email: email.toLowerCase(), password };
      }
    }
  }
  return null;
}

export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

/**
 * 解析多行文本（每行一个账号，支持与单行相同的分隔符）。
 */
export function parseAccountText(text: string): ParseResult {
  const accounts: ParsedAccount[] = [];
  const invalid: string[] = [];
  const seen = new Set<string>();

  for (const raw of text.split(/\r?\n/)) {
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const parsed = parseAccountLine(trimmed);
    if (!parsed) {
      invalid.push(trimmed);
      continue;
    }
    if (seen.has(parsed.email)) continue;
    seen.add(parsed.email);
    accounts.push(parsed);
  }
  return { accounts, invalid };
}
