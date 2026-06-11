import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold">류보살 v2</h1>
        <p className="mt-2 text-sm text-gray-600">
          LLM에 의존하지 않는 정밀 만세력 엔진으로 사주 원국·세력·용신 후보·대운/세운/월운과
          간지달력을 제공합니다. 입력 정보는 서버에 저장하지 않고 브라우저에 암호화 저장합니다.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link
          href="/manse"
          className="rounded-lg border bg-white p-6 shadow-sm transition hover:shadow"
        >
          <h2 className="text-lg font-semibold">만세력</h2>
          <p className="mt-1 text-sm text-gray-500">
            생년월일시·출생지로 사주 원국과 대운/세운/월운을 확인하고 용신을 검증합니다.
          </p>
        </Link>
        <Link
          href="/calendar"
          className="rounded-lg border bg-white p-6 shadow-sm transition hover:shadow"
        >
          <h2 className="text-lg font-semibold">간지달력</h2>
          <p className="mt-1 text-sm text-gray-500">
            날짜별 간지(한글·한자 병기)와 절기를 월 단위로 제공합니다.
          </p>
        </Link>
        <Link
          href="/chat"
          className="rounded-lg border bg-white p-6 shadow-sm transition hover:shadow"
        >
          <h2 className="text-lg font-semibold">대화형 통변</h2>
          <p className="mt-1 text-sm text-gray-500">
            엔진이 계산한 운의 신호를 근거와 함께 자연어로 풀이합니다. 같은 창에서 대화가
            이어집니다.
          </p>
        </Link>
      </div>
    </div>
  );
}
