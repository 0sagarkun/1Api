export default function handler(req, res) {
  res.status(200).json({
    quote: "The future depends on what you do today.",
    author: "Mahatma Gandhi"
  });
}
