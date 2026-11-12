export const metadata = {
  title: "CloudTrain",
  description: "CloudTrain web portal (stand-in)",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "0 auto", maxWidth: 860, padding: 24 }}>
        {children}
      </body>
    </html>
  );
}
