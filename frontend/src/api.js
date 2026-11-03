import axios from 'axios';
const api = axios.create({ baseURL: process.env.REACT_APP_API_URL || '', withCredentials: true, timeout: 20000 });
export default api;
