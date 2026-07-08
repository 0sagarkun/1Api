const quotes = [
  {
    quote: "The future depends on what you do today.",
    author: "Mahatma Gandhi"
  },
  {
    quote: "Believe you can and you're halfway there.",
    author: "Theodore Roosevelt"
  },
  {
    quote: "Hard work is worthless for those who don't believe in themselves.",
    author: "Naruto Uzumaki"
  },
  {
    quote: "Power comes in response to a need, not a desire.",
    author: "Goku"
  }
];

export default function handler(req, res) {
  const random = quotes[Math.floor(Math.random() * quotes.length)];
  res.status(200).json(random);
}
