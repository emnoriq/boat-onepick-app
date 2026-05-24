/**
 * /api/revalidate
 * スキャン完了後に GitHub Actions から呼び出してキャッシュを即時無効化する。
 * POST /api/revalidate
 * Header: Authorization: Bearer <REVALIDATE_SECRET>
 */
import { revalidateTag } from "next/cache";
import { NextRequest } from "next/server";

const TAGS = [
  "today-predictions",
  "stats",
  "ops-data",
  "schedule-data",
] as const;

export async function POST(request: NextRequest) {
  // 簡易認証（REVALIDATE_SECRET が未設定の場合は誰でも呼べる）
  const secret = process.env.REVALIDATE_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }
  }

  const body = await request.json().catch(() => ({}));
  // tag 指定があればそのタグのみ、なければ全タグを無効化
  const target: string[] = body?.tags ?? TAGS;
  for (const tag of target) {
    revalidateTag(tag);
  }

  return Response.json({
    ok: true,
    revalidated: target,
    at: new Date().toISOString(),
  });
}

// GET でもヘルスチェックとして使えるようにしておく
export async function GET() {
  return Response.json({ ok: true, tags: TAGS });
}
