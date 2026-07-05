import "./globals.css";
import type { Metadata } from "next";
import { AuthProvider } from "../lib/auth";
import Header from "../components/Header";

export const metadata: Metadata = {
  title: "WagyuTank — The Marketplace for Frozen Wagyu Genetics",
  description:
    "Buy and sell frozen Wagyu genetics — semen, embryos, and cloning rights. List in under a minute. Free.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Header />
          <main>{children}</main>
          <footer className="footer">
            <div className="container row wrap">
              <div>
                <strong className="gold">WagyuTank.com</strong> — the world's marketplace for frozen Wagyu genetics.
              </div>
              <div className="spacer" />
              <div className="row wrap faint" style={{ gap: 18 }}>
                <a href="/browse">Browse</a>
                <a href="/history">Breed History</a>
                <a href="/sell">Sell</a>
              </div>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
