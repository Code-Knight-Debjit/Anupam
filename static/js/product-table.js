const initExcelTable = () => {
  const root = document.querySelector('[data-excel-table-root]');
  if (!root) return;

  const shell = root.querySelector('[data-excel-shell]');
  const tableUrl = root.dataset.tableUrl || shell?.dataset.tableUrl;
  if (!tableUrl) return;

  const state = {
    page: 1,
    sort: '',
    direction: 'asc',
    filters: {},
  };

  // Track pending changes (not yet applied)
  let pendingChanges = false;

  const els = {
    shell,
    filters: root.querySelector('[data-excel-filters]'),
    apply: root.querySelector('[data-excel-apply]'),
    reset: root.querySelector('[data-excel-reset]'),
    status: root.querySelector('[data-excel-status]'),
    head: root.querySelector('[data-excel-head]'),
    body: root.querySelector('[data-excel-body]'),
    pagination: root.querySelector('[data-excel-pagination]'),
  };

  const notify = (message, type = 'success') => {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    }
  };

  const setStatus = (message, tone = 'neutral') => {
    if (!els.status) return;
    els.status.textContent = message;
    els.status.dataset.tone = tone;
  };

  const collectDraftFilters = () => {
    const draft = {};

    if (els.filters) {
      els.filters.querySelectorAll('select[data-filter-key], input[data-filter-key]').forEach((control) => {
        const filterKey = control.dataset.filterKey;
        if (control.tagName === 'SELECT') {
          draft[filterKey] = control.value;
        } else if (control.dataset.rangeRole) {
          if (!draft[filterKey]) {
            draft[filterKey] = { min: '', max: '' };
          }

          if (control.dataset.rangeRole === 'min') {
            draft[filterKey].min = control.value.trim();
          } else {
            draft[filterKey].max = control.value.trim();
          }
        }
      });
    }

    return draft;
  };

  const normalizeFilters = (filters) => {
    const cleaned = {};

    Object.entries(filters || {}).forEach(([key, value]) => {
      if (value && typeof value === 'object') {
        const min = value.min?.trim?.() || '';
        const max = value.max?.trim?.() || '';
        if (min !== '' || max !== '') {
          cleaned[key] = { min, max };
        }
        return;
      }

      const normalizedValue = String(value || '').trim();
      if (normalizedValue !== '') {
        cleaned[key] = normalizedValue;
      }
    });

    return cleaned;
  };

  const getPendingChangeCount = () => {
    const draft = normalizeFilters(collectDraftFilters());
    const applied = normalizeFilters(state.filters);
    return Object.keys(draft).reduce((count, key) => {
      const draftValue = draft[key];
      const appliedValue = applied[key] ?? '';
      return JSON.stringify(draftValue) === JSON.stringify(appliedValue) ? count : count + 1;
    }, 0);
  };

  const buildUrl = () => {
    const params = new URLSearchParams();
    if (state.page) params.set('page', String(state.page));
    if (state.sort) params.set('sort', state.sort);
    if (state.direction) params.set('direction', state.direction);
    Object.entries(state.filters).forEach(([key, value]) => {
      if (value && typeof value === 'object') {
        if (value.min !== '') params.set(`f_${key}_min`, value.min);
        if (value.max !== '') params.set(`f_${key}_max`, value.max);
        return;
      }

      if (value) params.set(`f_${key}`, value);
    });
    return `${tableUrl}?${params.toString()}`;
  };

  const makeButton = (label, className, onClick) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  };

  const updateApplyButtonState = () => {
    if (els.apply) {
      els.apply.classList.toggle('has-pending-changes', pendingChanges);
      els.apply.disabled = false;
      els.apply.setAttribute('aria-disabled', pendingChanges ? 'false' : 'false');
      els.apply.textContent = pendingChanges ? 'Apply Filters' : 'Apply Filters';
    }

    if (els.status) {
      if (pendingChanges) {
        const pendingCount = getPendingChangeCount();
        setStatus(`${pendingCount} filter${pendingCount === 1 ? '' : 's'} ready to apply.`, 'warning');
      } else {
        setStatus('Filters are up to date.', 'neutral');
      }
    }
  };

  const renderFilters = (filters) => {
    if (!els.filters) return;
    els.filters.innerHTML = '';

    if (!filters || filters.length === 0) {
      els.filters.hidden = true;
      return;
    }

    els.filters.hidden = false;

    filters.forEach((filter) => {
      const wrap = document.createElement('label');
      wrap.className = 'excel-spec-filter';

      const label = document.createElement('span');
      label.className = 'excel-spec-label';
      label.textContent = filter.label;

      if (filter.type === 'range') {
        const rangeWrap = document.createElement('div');
        rangeWrap.className = 'excel-spec-range';

        const minInput = document.createElement('input');
        minInput.className = 'form-input';
        minInput.type = 'number';
        minInput.step = 'any';
        minInput.inputMode = 'decimal';
        minInput.placeholder = 'Min';
        minInput.setAttribute('aria-label', `${filter.label} minimum`);
        minInput.dataset.filterKey = filter.key;
        minInput.dataset.rangeRole = 'min';
        minInput.value = state.filters[filter.key]?.min || filter.selected_min || '';

        const separator = document.createElement('span');
        separator.className = 'excel-spec-range-separator';
        separator.textContent = 'to';

        const maxInput = document.createElement('input');
        maxInput.className = 'form-input';
        maxInput.type = 'number';
        maxInput.step = 'any';
        maxInput.inputMode = 'decimal';
        maxInput.placeholder = 'Max';
        maxInput.setAttribute('aria-label', `${filter.label} maximum`);
        maxInput.dataset.filterKey = filter.key;
        maxInput.dataset.rangeRole = 'max';
        maxInput.value = state.filters[filter.key]?.max || filter.selected_max || '';

        const syncRange = () => {
          pendingChanges = JSON.stringify(normalizeFilters(collectDraftFilters())) !== JSON.stringify(normalizeFilters(state.filters));
          updateApplyButtonState();
        };

        const submitRangeOnEnter = (event) => {
          if (event.key === 'Enter' && pendingChanges) {
            event.preventDefault();
            applyFilters();
          }
        };

        minInput.addEventListener('input', syncRange);
        maxInput.addEventListener('input', syncRange);
        minInput.addEventListener('keydown', submitRangeOnEnter);
        maxInput.addEventListener('keydown', submitRangeOnEnter);

        rangeWrap.append(minInput, separator, maxInput);
        wrap.append(label, rangeWrap);

        const hint = document.createElement('div');
        hint.className = 'excel-spec-range-hint';
        hint.textContent = filter.min !== '' && filter.max !== '' ? `Range: ${filter.min} to ${filter.max}` : 'Range filter';
        wrap.appendChild(hint);
      } else {
        const select = document.createElement('select');
        select.className = 'form-input';
        select.setAttribute('aria-label', filter.label);
        select.dataset.filterKey = filter.key;

        const anyOption = document.createElement('option');
        anyOption.value = '';
        anyOption.textContent = 'All values';
        select.appendChild(anyOption);

        (filter.options || []).forEach((option) => {
          const optionNode = document.createElement('option');
          optionNode.value = option.value;
          optionNode.textContent = option.count > 1 ? `${option.label} (${option.count})` : option.label;
          select.appendChild(optionNode);
        });

        select.value = state.filters[filter.key] || filter.selected || '';
        select.addEventListener('change', () => {
          pendingChanges = JSON.stringify(normalizeFilters(collectDraftFilters())) !== JSON.stringify(normalizeFilters(state.filters));
          updateApplyButtonState();
        });
        select.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' && pendingChanges) {
            event.preventDefault();
            applyFilters();
          }
        });

        wrap.append(label, select);
      }

      els.filters.appendChild(wrap);
    });
  };

  const applyFilters = () => {
    const draftFilters = normalizeFilters(collectDraftFilters());

    if (JSON.stringify(draftFilters) === JSON.stringify(state.filters)) {
      pendingChanges = false;
      updateApplyButtonState();
      notify('No new filter changes to apply.', 'info');
      setStatus('No pending filter changes.', 'neutral');
      return;
    }

    state.filters = draftFilters;
    state.page = 1;
    pendingChanges = false;
    updateApplyButtonState();
    setStatus('Applying filters...', 'loading');
    notify('Applying filters.', 'success');
    loadTable();
  };

  const resetFilters = () => {
    state.page = 1;
    state.sort = '';
    state.direction = 'asc';
    state.filters = {};
    pendingChanges = false;

    if (els.filters) {
      els.filters.querySelectorAll('select[data-filter-key], input[data-filter-key]').forEach((control) => {
        control.value = '';
      });
    }

    updateApplyButtonState();
    setStatus('Filters cleared. Showing the full table.', 'neutral');
    notify('Filters cleared.', 'success');
    loadTable();
  };

  const renderHead = (columns, sorting) => {
    if (!els.head) return;
    els.head.innerHTML = '';

    const row = document.createElement('tr');
    (columns || []).forEach((column) => {
      const th = document.createElement('th');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'excel-spec-sort-btn';

      const label = document.createElement('span');
      label.textContent = column.label;

      const indicator = document.createElement('span');
      indicator.className = 'excel-spec-sort-indicator';
      indicator.textContent = sorting && sorting.key === column.key ? (sorting.direction === 'desc' ? '↓' : '↑') : '↕';

      button.append(label, indicator);
      button.addEventListener('click', () => {
        if (state.sort === column.key) {
          state.direction = state.direction === 'asc' ? 'desc' : 'asc';
        } else {
          state.sort = column.key;
          state.direction = 'asc';
        }
        state.page = 1;
        loadTable();
      });

      th.appendChild(button);
      row.appendChild(th);
    });

    els.head.appendChild(row);
  };

  const renderBody = (rows, columns) => {
    if (!els.body) return;
    els.body.innerHTML = '';

    if (!rows || rows.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = Math.max(columns.length, 1);
      td.className = 'excel-spec-empty';
      td.innerHTML = '<strong>No matching rows</strong><span>Adjust the filters or search terms to widen the result set.</span>';
      tr.appendChild(td);
      els.body.appendChild(tr);
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement('tr');
      columns.forEach((column) => {
        const td = document.createElement('td');
        td.className = 'excel-spec-cell';
        const value = row.values?.[column.key] || '';
        td.textContent = value || '—';
        if (!value) td.classList.add('excel-spec-cell-muted');
        tr.appendChild(td);
      });
      els.body.appendChild(tr);
    });
  };

  const renderPagination = (pagination) => {
    if (!els.pagination) return;
    els.pagination.innerHTML = '';

    const total = pagination?.total || 0;
    const totalPages = pagination?.total_pages || 1;
    const currentPage = pagination?.page || 1;
    const pageNumbers = pagination?.page_numbers || Array.from({ length: totalPages }, (_, index) => index + 1);

    const info = document.createElement('div');
    info.className = 'excel-spec-pagination-info';
    info.textContent = total > 0
      ? `Showing page ${currentPage} of ${totalPages} · ${total} row${total === 1 ? '' : 's'}`
      : 'No rows available';

    const prev = makeButton('Previous', 'btn btn-ghost btn-sm', () => {
      if (state.page > 1) {
        state.page -= 1;
        loadTable();
      }
    });
    prev.disabled = currentPage <= 1;

    const next = makeButton('Next', 'btn btn-primary btn-sm', () => {
      if (currentPage < totalPages) {
        state.page += 1;
        loadTable();
      }
    });
    next.disabled = currentPage >= totalPages;

    const actions = document.createElement('div');
    actions.className = 'excel-spec-pagination-actions';

    actions.append(prev);

    pageNumbers.forEach((pageNumber) => {
      const button = makeButton(String(pageNumber), pageNumber === currentPage ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm', () => {
        state.page = pageNumber;
        loadTable();
      });
      button.disabled = pageNumber === currentPage;
      actions.append(button);
    });

    actions.append(next);
    els.pagination.append(info, actions);
  };

  const renderError = (message) => {
    if (!els.body) return;
    const columnCount = Math.max(els.head?.querySelectorAll('th').length || 0, 1);
    els.head.innerHTML = '';
    els.filters.innerHTML = '';
    els.body.innerHTML = '';
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = columnCount;
    td.className = 'excel-spec-error';
    const title = document.createElement('strong');
    title.textContent = 'Unable to load table';
    const body = document.createElement('span');
    body.textContent = message;
    td.append(title, body);
    tr.appendChild(td);
    els.body.appendChild(tr);
  };

  const loadTable = async () => {
    if (els.shell) els.shell.classList.add('is-loading');
    if (pendingChanges) {
      setStatus('You have unapplied filter changes.', 'warning');
    } else if (!els.status?.textContent) {
      setStatus('Loading specification table...', 'loading');
    }

    try {
      const response = await fetch(buildUrl(), {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const payload = await response.json();

      if (!response.ok || !payload.success) {
        throw new Error(payload.message || 'Unable to load the specification table.');
      }

      const table = payload.table;
      renderFilters(table.filters);
      renderHead(table.columns, table.sorting);
      renderBody(table.rows, table.columns);
      renderPagination(table.pagination);
      if (!pendingChanges) {
        setStatus(`Showing ${table.pagination?.total || 0} matching row${(table.pagination?.total || 0) === 1 ? '' : 's'}.`, 'success');
      }
    } catch (error) {
      renderError(error.message || 'Unable to load the specification table.');
      setStatus(error.message || 'Unable to load the specification table.', 'error');
      notify(error.message || 'Unable to load the specification table.', 'error');
    } finally {
      if (els.shell) els.shell.classList.remove('is-loading');
    }
  };

  if (els.apply) {
    els.apply.addEventListener('click', applyFilters);
  }

  if (els.reset) {
    els.reset.addEventListener('click', resetFilters);
  }

  updateApplyButtonState();

  loadTable();
};

initExcelTable();