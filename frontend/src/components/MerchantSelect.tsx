import { useEffect, useState } from "react";
import { api } from "../api/client";
import { MerchantOption } from "../api/types";
import { useLang } from "../i18n";

interface Props {
  value: string;
  onChange: (merchantId: string) => void;
}

/** Merchant filter dropdown for the admin pages (orders, calls, audit log). */
export default function MerchantSelect({ value, onChange }: Props) {
  const { t } = useLang();
  const [options, setOptions] = useState<MerchantOption[]>([]);

  useEffect(() => {
    api<MerchantOption[]>("/api/admin/merchants/options")
      .then(setOptions)
      .catch(() => {});
  }, []);

  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("সব মার্চেন্ট")}</option>
      {options.map((m) => (
        <option key={m.id} value={m.id}>
          {m.business_name}
          {m.active ? "" : ` (${t("নিষ্ক্রিয়")})`}
        </option>
      ))}
    </select>
  );
}
