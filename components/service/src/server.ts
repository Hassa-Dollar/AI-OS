import { createApp } from './app';
import { routes } from './routes/index';

const port = Number(process.env.PORT ?? 3000);
createApp(routes).listen(port, () => {
  console.log(`listening on :${port}`);
});
