// Renders a URL as a scannable QR code, entirely client-side — the backend
// only ever hands back the plain export URL string (see anki_server.py's
// rationale for why nothing heavier is generated server-side).

import qrcode from "qrcode-generator";
import { FC, useMemo } from "react";

export const QrCode: FC<{ value: string; size?: number }> = ({ value, size = 200 }) => {
  const svg = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(value);
    qr.make();
    return qr.createSvgTag({ scalable: true });
  }, [value]);

  return (
    <div
      style={{
        width: size,
        height: size,
        background: "#fff",
        padding: 8,
        borderRadius: 4,
        boxSizing: "border-box",
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};
