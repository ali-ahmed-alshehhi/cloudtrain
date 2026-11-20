import "./globals.css";

export const metadata = {
  title: "CloudTrain | ML workspace",
  description: "Projects, datasets and training in one CloudTrain workspace.",
};

export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
