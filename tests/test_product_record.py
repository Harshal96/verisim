from __future__ import annotations

from verisim import CompanyRecord, DatasetSpec, Product, ProductRecord, Verisim


def test_product_record_generates_coherent_b2b_offering():
    product = Verisim(locale="en_US", seed=91).generate(ProductRecord)

    compact = product.as_product()
    feature_set = set(product.features)

    assert compact == Product(
        id=product.id,
        company_id=product.company.id,
        name=product.name,
        slug=product.slug,
        industry=product.industry,
        category=product.category,
        website=product.website,
    )
    assert product.company.id == compact.company_id
    assert product.company.industry == product.industry
    assert product.website.host == product.company.domain
    assert (
        product.website.url
        == f"https://{product.company.domain}/products/{product.slug}"
    )
    assert product.owner_department
    assert product.target_departments
    assert feature_set
    assert len(product.plans) in {2, 3}
    assert all(plan.included_features for plan in product.plans)
    assert all(
        set(plan.included_features).issubset(feature_set) for plan in product.plans
    )
    assert all(plan.price_range.currency == "USD" for plan in product.plans)
    assert all(
        plan.price_range.amount_min_usd <= plan.price_range.amount_max_usd
        for plan in product.plans
    )


def test_product_record_uses_company_record_context():
    verisim = Verisim(locale="en_US", seed=92)
    company = verisim.generate(
        CompanyRecord, context={"size_band": "startup", "founded_year": 2021}
    )

    product = verisim.generate(ProductRecord, context={"company": company})

    assert product.company.id == company.id
    assert product.company.domain == company.domain
    assert product.industry == company.industry
    assert product.owner_department in company.departments
    assert set(product.target_departments).issubset(set(company.departments))
    assert product.target_size_band == company.size_band
    assert product.launch_year >= company.founded_year
    assert len(product.plans) == 2


def test_product_record_context_can_return_record_or_expand_product_facts():
    verisim = Verisim(seed=93)
    record = verisim.generate(ProductRecord)

    same_record = verisim.generate(ProductRecord, context=record)
    compact = verisim.generate(Product, context=record)

    assert same_record is record
    assert compact == record.as_product()


def test_dataset_generation_can_attach_products_to_generated_companies():
    verisim = Verisim(locale="en_US", seed=94)

    dataset = verisim.dataset(DatasetSpec(people=4, companies=2, products=5))

    company_ids = {company.id for company in dataset.companies}
    assert len(dataset.people) == 4
    assert len(dataset.companies) == 2
    assert len(dataset.products) == 5
    assert all(product.company.id in company_ids for product in dataset.products)
    assert len({product.id for product in dataset.products}) == 5
    skus = {plan.sku for product in dataset.products for plan in product.plans}
    assert len(skus) == sum(len(product.plans) for product in dataset.products)


def test_product_record_generation_is_deterministic_for_seed():
    first = Verisim(locale="en_US", seed=95).generate(ProductRecord)
    second = Verisim(locale="en_US", seed=95).generate(ProductRecord)

    assert first.name == second.name
    assert first.slug == second.slug
    assert first.pricing_model == second.pricing_model
    assert [plan.sku for plan in first.plans] == [plan.sku for plan in second.plans]
    assert [plan.price_range for plan in first.plans] == [
        plan.price_range for plan in second.plans
    ]


def test_lite_pack_can_generate_10k_unique_products_for_one_company():
    verisim = Verisim(locale="en_US", seed=96)
    company = verisim.generate(CompanyRecord, context={"size_band": "mid-market"})

    products = verisim.records(
        ProductRecord, count=10_000, context={"company": company}
    )

    assert len(products) == 10_000
    assert all(product.company.id == company.id for product in products)
    assert len({product.id for product in products}) == 10_000
    assert len({product.name for product in products}) == 10_000
    assert len({product.slug for product in products}) == 10_000
    assert len({product.website.url for product in products}) == 10_000
    assert len({product.category for product in products}) >= 12
    assert len({plan.sku for product in products for plan in product.plans}) == (
        sum(len(product.plans) for product in products)
    )
