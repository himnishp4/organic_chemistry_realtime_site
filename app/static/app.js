(() => {
  const indicator = document.getElementById('live-indicator');
  if (!document.body.dataset.livePage || !window.EventSource) return;

  let firstMessage = true;
  let source;

  const connect = () => {
    source = new EventSource('/events');
    source.onopen = () => indicator?.classList.add('connected');
    source.onmessage = () => {
      if (firstMessage) {
        firstMessage = false;
        return;
      }
      if (indicator) {
        indicator.innerHTML = '<span></span> New teacher update';
        indicator.classList.add('updated');
      }
      window.setTimeout(() => window.location.reload(), 550);
    };
    source.onerror = () => indicator?.classList.remove('connected');
  };
  connect();
})();
