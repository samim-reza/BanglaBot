import { MerchantGate } from "@/components/merchant-gate";
import { MerchantShell } from "@/components/merchant-shell";

export default function MerchantLayout({ children }: { children: React.ReactNode }) {
  return (
    <MerchantGate>
      <MerchantShell>{children}</MerchantShell>
    </MerchantGate>
  );
}
