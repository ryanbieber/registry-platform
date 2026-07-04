type SearchFiltersProps = {
  onSearch?: () => void;
};

export function SearchFilters({ onSearch }: SearchFiltersProps) {
  return (
    <section className="panel">
      <h2>Search filters</h2>
      <div className="filters-grid">
        <input placeholder="Name" />
        <input placeholder="State" />
        <input placeholder="Risk level" />
        <button type="button" onClick={onSearch}>
          Run search
        </button>
      </div>
    </section>
  );
}
