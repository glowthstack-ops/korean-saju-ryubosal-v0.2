import { getCalendar } from "@/lib/api";
import { CalendarGrid, DateJump, MonthNav } from "@/components/calendar/CalendarGrid";

export const revalidate = 3600;

export default async function CalendarMonthPage({
  params,
}: {
  params: { year: string; month: string };
}) {
  const year = Number(params.year);
  const month = Number(params.month);

  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    return <p className="text-sm text-red-600">잘못된 연·월입니다.</p>;
  }

  let data;
  try {
    data = await getCalendar(year, month);
  } catch {
    return (
      <p className="text-sm text-red-600">
        달력을 불러오지 못했습니다. 백엔드 API가 실행 중인지 확인하세요.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <DateJump />
      <MonthNav year={year} month={month} />
      <CalendarGrid data={data} />
      <p className="text-xs text-gray-400">
        간지는 KST 만세력 기준(절기·입춘 경계 반영). 한자/한글 병기.
      </p>
    </div>
  );
}
