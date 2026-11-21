from uuid import UUID


class ProductUrlAlreadyExists(Exception):
    def __init__(self, product_id: UUID,):
        self._product_id = product_id
        
        super().__init__("A product with this URL already exists.")


class ImportJobNotFoundError(Exception):
    def __init__(self, job_id: UUID,):
        self.job_id = job_id
            
        super().__init__(f"A job with id={job_id} was not found.")