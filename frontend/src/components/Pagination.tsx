import { useLang } from "../i18n";

export default function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const { t, fmtNum } = useLang();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span>
        {t("মোট {total} টি — পৃষ্ঠা {page}/{pages}", {
          total: fmtNum(total),
          page: fmtNum(page),
          pages: fmtNum(pages),
        })}
      </span>
      <button className="btn secondary small" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ← {t("আগের")}
      </button>
      <button
        className="btn secondary small"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        {t("পরের")} →
      </button>
    </div>
  );
}
