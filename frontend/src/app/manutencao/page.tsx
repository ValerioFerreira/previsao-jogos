import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Manutenção · ApostaInfo",
  description: "Estamos trabalhando para melhorar sua experiência.",
};

export default function ManutencaoPage() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center">
      <div className="w-full max-w-lg px-6 py-12 flex flex-col items-center text-center gap-6">
        <div className="flex items-center gap-2">
          <img src="/images/so-o-A-sem-fundo.png" alt="ApostaInfo" className="w-10 h-10 object-contain" />
          <img src="/images/so-o-texto-sem-fundo.png" alt="ApostaInfo" className="h-8 w-auto object-contain" />
        </div>

        <div className="scene" aria-hidden="true">
          <div className="gear gear-a">⚙</div>
          <div className="gear gear-b">⚙</div>

          <div className="card">
            <div className="bar bar-badge" />
            <div className="bar bar-1" />
            <div className="bar bar-2" />
            <div className="bar bar-3 short" />
          </div>

          <div className="bot bot-1">
            <span className="antenna" />
            <span className="head">
              <span className="eye eye-l" />
              <span className="eye eye-r" />
            </span>
            <span className="body" />
            <span className="arm">
              <span className="tool" />
            </span>
          </div>

          <div className="bot bot-2">
            <span className="antenna" />
            <span className="head">
              <span className="eye eye-l" />
              <span className="eye eye-r" />
            </span>
            <span className="body" />
            <span className="arm">
              <span className="tool" />
            </span>
          </div>

          <div className="bot bot-3">
            <span className="antenna" />
            <span className="head">
              <span className="eye eye-l" />
              <span className="eye eye-r" />
            </span>
            <span className="body" />
            <span className="arm">
              <span className="tool" />
            </span>
          </div>

          <span className="spark spark-1">✦</span>
          <span className="spark spark-2">✦</span>
          <span className="spark spark-3">✦</span>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Sistema em Manutenção
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground max-w-md">
            Estamos trabalhando para melhorar sua experiência, e já já estamos de volta!
          </p>
        </div>

        <a
          href="/"
          className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-medium px-5 py-2.5 hover:opacity-90 transition-opacity"
        >
          Tentar novamente
        </a>
      </div>

      <style>{`
        .scene {
          position: relative;
          width: 100%;
          max-width: 320px;
          height: 200px;
          margin: 0.5rem auto 0;
        }

        .card {
          position: absolute;
          left: 50%;
          top: 8px;
          transform: translateX(-50%);
          width: 170px;
          height: 92px;
          background: hsl(var(--card));
          border: 1px solid hsl(var(--border));
          border-radius: var(--radius);
          box-shadow: 0 6px 18px -6px hsl(220 15% 10% / 0.15);
          padding: 12px;
          animation: card-shake 3.2s ease-in-out infinite;
        }

        .card .bar {
          height: 8px;
          border-radius: 5px;
          background: hsl(var(--muted));
          margin-bottom: 8px;
          animation: fix-flash 3.2s ease-in-out infinite;
        }
        .card .bar-badge {
          width: 22px;
          height: 22px;
          border-radius: 999px;
          margin-bottom: 10px;
        }
        .card .bar-1 { width: 90%; animation-delay: 0.1s; }
        .card .bar-2 { width: 70%; animation-delay: 0.3s; }
        .card .bar-3 { width: 45%; animation-delay: 0.5s; }

        @keyframes card-shake {
          0%, 60%, 100% { transform: translateX(-50%) rotate(0deg); }
          62% { transform: translateX(-50%) rotate(-1.5deg); }
          64% { transform: translateX(-50%) rotate(1.5deg); }
          66% { transform: translateX(-50%) rotate(0deg); }
        }

        @keyframes fix-flash {
          0%, 65%, 100% { background: hsl(var(--muted)); }
          75%, 85% { background: hsl(var(--primary) / 0.55); }
        }

        .gear {
          position: absolute;
          font-size: 20px;
          line-height: 1;
          color: hsl(var(--primary) / 0.45);
          animation: spin 6s linear infinite;
        }
        .gear-a { top: 4px; right: 18px; font-size: 24px; }
        .gear-b { top: 26px; right: 0; font-size: 14px; animation-direction: reverse; animation-duration: 4s; }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .bot {
          position: absolute;
          bottom: 6px;
          width: 30px;
          height: 48px;
          animation: bob 1.6s ease-in-out infinite;
        }
        .bot-1 { left: 30px; animation-delay: 0s; }
        .bot-2 { left: 130px; animation-delay: 0.4s; }
        .bot-3 { left: 220px; width: 26px; height: 40px; animation-delay: 0.8s; }

        @keyframes bob {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-3px); }
        }

        .bot .antenna {
          position: absolute;
          top: -8px;
          left: 50%;
          transform: translateX(-50%);
          width: 3px;
          height: 8px;
          background: hsl(var(--muted-foreground));
          border-radius: 2px;
        }
        .bot .antenna::before {
          content: "";
          position: absolute;
          top: -5px;
          left: 50%;
          transform: translateX(-50%);
          width: 6px;
          height: 6px;
          border-radius: 999px;
          background: hsl(var(--primary));
          animation: blink 1.6s ease-in-out infinite;
        }

        .bot .head {
          position: absolute;
          top: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 22px;
          height: 16px;
          border-radius: 6px;
          background: hsl(var(--foreground) / 0.85);
        }
        .bot .eye {
          position: absolute;
          top: 6px;
          width: 4px;
          height: 4px;
          border-radius: 999px;
          background: hsl(var(--primary));
        }
        .bot .eye-l { left: 4px; }
        .bot .eye-r { right: 4px; }

        .bot .body {
          position: absolute;
          top: 17px;
          left: 50%;
          transform: translateX(-50%);
          width: 20px;
          height: 22px;
          border-radius: 5px;
          background: hsl(var(--foreground) / 0.7);
        }

        .bot .arm {
          position: absolute;
          top: 19px;
          right: -6px;
          width: 12px;
          height: 3px;
          border-radius: 2px;
          background: hsl(var(--foreground) / 0.7);
          transform-origin: left center;
          animation: swing 1.6s ease-in-out infinite;
        }
        .bot .tool {
          position: absolute;
          right: -3px;
          top: -5px;
          width: 4px;
          height: 12px;
          border-radius: 2px;
          background: hsl(43 74% 55%);
        }

        @keyframes swing {
          0%, 100% { transform: rotate(-6deg); }
          50% { transform: rotate(48deg); }
        }

        @keyframes blink {
          0%, 80%, 100% { opacity: 1; }
          90% { opacity: 0.25; }
        }

        .spark {
          position: absolute;
          font-size: 12px;
          color: hsl(43 74% 55%);
          opacity: 0;
          animation: spark-pop 1.6s ease-in-out infinite;
        }
        .spark-1 { top: 40px; left: 56px; animation-delay: 0.6s; }
        .spark-2 { top: 34px; left: 152px; animation-delay: 1.0s; }
        .spark-3 { top: 46px; left: 236px; animation-delay: 1.4s; }

        @keyframes spark-pop {
          0%, 55% { opacity: 0; transform: scale(0.3) translateY(4px); }
          65% { opacity: 1; transform: scale(1.1) translateY(-4px); }
          80% { opacity: 0.8; transform: scale(0.9) translateY(-8px); }
          100% { opacity: 0; transform: scale(0.5) translateY(-12px); }
        }

        @media (prefers-reduced-motion: reduce) {
          .card, .card .bar, .gear, .bot, .bot .arm, .bot .antenna::before, .spark {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}
