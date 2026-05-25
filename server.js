const express = require('express');
const cors = require('cors');
const path = require('path');
const stockRoutes = require('./routes/stocks');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname)));

app.use('/api/stocks', stockRoutes);

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`台股儀表板伺服器啟動中: http://localhost:${PORT}`);
});
