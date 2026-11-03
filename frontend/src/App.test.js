import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import api from './api';
import App from './App';
jest.mock('./api', () => ({ get: jest.fn(), post: jest.fn(), delete: jest.fn() }));
beforeEach(() => {
  jest.clearAllMocks(); sessionStorage.clear(); localStorage.clear();
  api.post.mockResolvedValue({ data: { venues: [], total: 0, page: 1, pages: 1 } });
  api.get.mockImplementation(path => Promise.resolve({ data: path === '/api/session' ? { user: null, guestUsed: 0, guestLimit: 2, retentionHours: 24 } : { history: [] } }));
});
test('external search is opt-in and credentials are retired', async () => {
  localStorage.setItem('research_analyzer_token', 'old-token');
  render(<App />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze paper' })).toBeEnabled());
  expect(screen.getByRole('checkbox', { name: /external OpenAlex/ })).not.toBeChecked();
  expect(localStorage.getItem('research_analyzer_token')).toBeNull();
});
test('missing upload is explained', async () => {
  render(<App />);
  const button = screen.getByRole('button', { name: 'Analyze paper' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  expect(await screen.findByRole('alert')).toHaveTextContent('Please select a PDF');
});
test('queued analysis can be cancelled and deleted', async () => {
  api.post.mockResolvedValue({ data: { job_id: 'test-job' } });
  api.delete.mockResolvedValue({ data: { ok: true } });
  api.get.mockImplementation(path => Promise.resolve({ data: path === '/api/session' ? { user: null, guestUsed: 0, guestLimit: 2 } : path.startsWith('/api/status') ? { status: 'queued' } : { history: [] } }));
  render(<App />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze paper' })).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Upload research paper'), { target: { files: [new File(['%PDF-test'], 'paper.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Analyze paper' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel and delete analysis' }));
  await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/analyses/test-job'));
  await waitFor(() => expect(sessionStorage.getItem('active_analysis')).toBeNull());
});
test('completed analysis displays observations without inventing a quality score', async () => {
  sessionStorage.setItem('active_analysis', 'complete-job');
  api.get.mockImplementation(path => Promise.resolve({ data: path === '/api/session' ? { user: null, guestUsed: 1, guestLimit: 2 } : path.startsWith('/api/status') ? {
    status: 'finished', result: { score: null, disclaimer: 'Not peer review.', features: { word_count: 500, sentence_count: 25, readability: 35, citation_markers: 2 },
      detected_sections: ['Abstract'], domain_stats: { domain: 'General Research' }, recommendations: [], summary: 'An extractive summary.', reference_search: { method: 'tfidf' }, reference_papers: [] }
  } : { history: [] } }));
  render(<App />);
  expect(await screen.findByText('An extractive summary.')).toBeInTheDocument();
  expect(screen.getByText('Not peer review.')).toBeInTheDocument();
  expect(screen.queryByText('Overall Score')).not.toBeInTheDocument();
});

test('invalid dropped files are rejected before submission', async () => {
  const { container } = render(<App />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze paper' })).toBeEnabled());
  fireEvent.drop(container.querySelector('.upload-zone'), { dataTransfer: { files: [new File(['text'], 'notes.txt')] } });
  expect(await screen.findByRole('alert')).toHaveTextContent('Choose a non-empty PDF');
  expect(api.post.mock.calls.some(([path]) => path === '/api/analyze')).toBe(false);
});

test('failed session loads can be retried without reloading the page', async () => {
  api.get.mockRejectedValueOnce(new Error('offline'));
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry connection' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Analyze paper' })).toBeEnabled());
});
