import { OrderStatus, STATUS_LABELS } from "../api/types";
import { useLang } from "../i18n";

export default function StatusBadge({ status }: { status: OrderStatus }) {
  const { t } = useLang();
  return <span className={`badge ${status}`}>{t(STATUS_LABELS[status])}</span>;
}
